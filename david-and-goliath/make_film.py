#!/usr/bin/env python3
"""Make the whole David and Goliath film with Google Veo, end to end.

Steps (each skips work that is already done, so it is safe to re-run):

    portraits  make one reference picture of David and one of Goliath (Imagen)
    clips      generate every clip from shots.json (Veo), attaching the
               portraits of the characters in each shot so faces stay the same
    film       join the clips in order into output/david-and-goliath.mp4
    all        portraits, then clips, then film
    plan       show what will be generated and what is already done (free)

Needs:  pip install google-genai   and   ffmpeg on PATH
        GEMINI_API_KEY (or GOOGLE_API_KEY) set in the environment

Examples:

    python3 david-and-goliath/make_film.py plan
    python3 david-and-goliath/make_film.py all
    python3 david-and-goliath/make_film.py clips --only 03,18a --takes 3
    python3 david-and-goliath/make_film.py film --music music.mp3

Choosing takes: the first take of shot 3 is output/clips/shot-03.mp4 and
extra takes are shot-03.take2.mp4, shot-03.take3.mp4. To use a different
take, copy it over shot-03.mp4 and run `film` again.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from build_prompts import build_prompt, clip_prompts, load_data

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
REFS = OUT / "refs"
CLIPS = OUT / "clips"
FILM = OUT / "david-and-goliath.mp4"
FAILED = OUT / "failed.json"

CLIP_SECONDS = 8
# Characters that get a reference portrait (Veo accepts up to three per clip).
PORTRAIT_CAST = ["DAVID", "GOLIATH"]
NEGATIVE_PROMPT = "on-screen text, subtitles, captions, watermark, background music, cartoon, animation, blood, gore"
# The prompt sheet's advice when the app refuses a battle shot: cut to the
# soldiers' faces watching instead. Used only for narrated shots, where the
# narration still fits over the new picture.
FALLBACK_ACTION = (
    "Close-up of the faces of the ISRAELITE SOLDIERS on the hillside, watching the "
    "valley below in tense silence, wind moving their hair and cloaks."
)
FALLBACK_CAST = ["ISRAELITE_SOLDIERS"]


def log(msg):
    print(msg, flush=True)


# --- Google API ----------------------------------------------------------

def client():
    try:
        from google import genai
    except ImportError:
        sys.exit("Missing package: run  pip install google-genai")
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("Set GEMINI_API_KEY to your Gemini API key (https://aistudio.google.com/apikey)")
    return genai.Client()


def with_retries(call, what):
    """Retry rate-limit and server errors with backoff; re-raise anything else."""
    from google.genai import errors

    for attempt in range(6):
        try:
            return call()
        except errors.APIError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 5:
                raise
            wait = 30 * 2 ** attempt
            log(f"  {what}: {e.code} {e.message or ''} — retrying in {wait}s")
            time.sleep(wait)


def make_portraits(api, data, model):
    from google.genai import types

    REFS.mkdir(parents=True, exist_ok=True)
    for key in PORTRAIT_CAST:
        path = REFS / f"{key.lower()}.png"
        if path.exists():
            log(f"portrait {path.name}: already done")
            continue
        prompt = (
            f'{data["style"]}\n\n{data["characters"][key]}\n\n'
            "Full-length character reference photo: standing, facing the camera, whole body "
            "and face clearly visible, plain sandy background, soft even daylight."
        )
        log(f"portrait {path.name}: generating with {model}")
        resp = with_retries(
            lambda: api.models.generate_images(
                model=model,
                prompt=prompt,
                config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16"),
            ),
            path.name,
        )
        images = resp.generated_images or []
        if not images or images[0].image is None:
            reason = images[0].rai_filtered_reason if images else "no image returned"
            sys.exit(f"portrait {path.name} was refused: {reason}")
        images[0].image.save(str(path))
        log(f"portrait {path.name}: saved")


def generate_video(api, model, prompt, refs, resolution, dest):
    """Run one Veo generation. Returns None on success, else the refusal reason."""
    from google.genai import types

    config = types.GenerateVideosConfig(
        aspect_ratio="16:9",
        duration_seconds=CLIP_SECONDS,
        resolution=resolution,
        negative_prompt=NEGATIVE_PROMPT,
        number_of_videos=1,
    )
    if refs:
        config.reference_images = [
            types.VideoGenerationReferenceImage(
                image=types.Image.from_file(location=str(p)), reference_type="asset"
            )
            for p in refs
        ]
    op = with_retries(
        lambda: api.models.generate_videos(model=model, prompt=prompt, config=config), dest.name
    )
    started = time.time()
    while not op.done:
        if time.time() - started > 20 * 60:
            return "timed out after 20 minutes"
        time.sleep(10)
        op = with_retries(lambda: api.operations.get(op), dest.name)
    if op.error:
        return f"error: {op.error}"
    videos = (op.response.generated_videos if op.response else None) or []
    if not videos:
        reasons = op.response.rai_media_filtered_reasons if op.response else None
        return f"refused: {reasons or 'no video returned'}"
    api.files.download(file=videos[0].video)
    tmp = dest.with_suffix(".part.mp4")
    videos[0].video.save(str(tmp))
    tmp.replace(dest)
    return None


def take_path(clip_id, take):
    return CLIPS / (f"shot-{clip_id}.mp4" if take == 1 else f"shot-{clip_id}.take{take}.mp4")


def make_clips(api, data, model, resolution, takes, only, use_refs):
    CLIPS.mkdir(parents=True, exist_ok=True)
    failed = json.loads(FAILED.read_text()) if FAILED.exists() else {}
    jobs = [(cid, shot, prompt) for cid, shot, prompt in clip_prompts(data) if not only or cid in only]
    for n, (clip_id, shot, prompt) in enumerate(jobs, 1):
        refs = [REFS / f"{k.lower()}.png" for k in PORTRAIT_CAST if k in shot["cast"]] if use_refs else []
        missing_refs = [p for p in refs if not p.exists()]
        if missing_refs:
            sys.exit(f"Missing portrait {missing_refs[0]} — run the `portraits` step first, or pass --no-refs")
        for take in range(1, takes + 1):
            dest = take_path(clip_id, take)
            label = f"[{n}/{len(jobs)}] shot {clip_id} take {take}"
            if dest.exists():
                log(f"{label}: already done")
                continue
            log(f"{label}: generating ({shot['title']})")
            reason = generate_video(api, model, prompt, refs, resolution, dest)
            if reason and shot["speaker"] == "NARRATOR":
                log(f"{label}: {reason} — trying the soldiers-watching fallback")
                line = None
                if shot.get("split"):
                    line = shot["split"]["ab".index(clip_id[-1])]
                fallback = build_prompt(shot, data, line=line, action=FALLBACK_ACTION, cast=FALLBACK_CAST)
                reason = generate_video(api, model, fallback, [], resolution, dest)
            if reason:
                log(f"{label}: FAILED — {reason}")
                failed[f"{clip_id} take {take}"] = reason
            else:
                failed.pop(f"{clip_id} take {take}", None)
                log(f"{label}: saved {dest.relative_to(HERE)}")
            FAILED.write_text(json.dumps(failed, indent=2))
    if failed:
        log(f"\n{len(failed)} clip(s) failed — see {FAILED.relative_to(HERE)}. "
            "Edit those shots in shots.json (or make them in another app and save them "
            "as output/clips/shot-NN.mp4), then run again.")
    else:
        FAILED.unlink(missing_ok=True)


# --- ffmpeg --------------------------------------------------------------

def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def probe(path, entries):
    out = subprocess.run(
        ["ffprobe", "-v", "error", *entries, "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return out.strip()


def duration(path):
    return float(probe(path, ["-show_entries", "format=duration"]))


def has_audio(path):
    return bool(probe(path, ["-select_streams", "a", "-show_entries", "stream=index"]))


def make_film(data, music, music_volume, allow_missing, size):
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not installed")
    w, h = size.split("x")
    ids = [cid for cid, _, _ in clip_prompts(data)]
    paths = [take_path(cid, 1) for cid in ids]
    missing = [cid for cid, p in zip(ids, paths) if not p.exists()]
    if missing and not allow_missing:
        sys.exit(f"Missing clips: {', '.join(missing)} — generate them, or pass --allow-missing")
    paths = [p for p in paths if p.exists()]
    if not paths:
        sys.exit("No clips to join yet")

    work = OUT / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    # Re-encode every clip to one format so they join cleanly.
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
          "setsar=1,fps=24,format=yuv420p")
    parts = []
    for i, src in enumerate(paths):
        dst = work / f"{i:03d}.mp4"
        log(f"preparing {src.name}")
        cmd = ["ffmpeg", "-y", "-i", str(src)]
        if has_audio(src):
            cmd += ["-map", "0:v:0", "-map", "0:a:0"]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v:0", "-map", "1:a", "-shortest"]
        cmd += ["-vf", vf, "-af", "aresample=48000", "-ac", "2",
                "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k", str(dst)]
        run(cmd)
        parts.append(dst)

    joined = work / "joined.mp4"
    (work / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"), "-c", "copy", str(joined)])

    # Final pass: fade in from black, fade out at the end, optional music bed.
    total = duration(joined)
    end = max(total - 2, 0)
    cmd = ["ffmpeg", "-y", "-i", str(joined)]
    graph = f"[0:v]fade=t=in:d=1,fade=t=out:st={end:.2f}:d=2[v];[0:a]afade=t=in:d=1,afade=t=out:st={end:.2f}:d=2"
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        graph += (f"[a0];[1:a]volume={music_volume},atrim=0:{total:.2f},afade=t=in:d=2,"
                  f"afade=t=out:st={max(total - 4, 0):.2f}:d=4[m];[a0][m]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        graph += "[a]"
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(FILM)]
    log("joining clips")
    run(cmd)
    shutil.rmtree(work)
    log(f"Film saved: {FILM} ({len(parts)} clips, {total / 60:.1f} min)")


def plan(data, takes):
    rows = list(clip_prompts(data))
    todo = 0
    for cid, shot, _ in rows:
        done = [t for t in range(1, takes + 1) if take_path(cid, t).exists()]
        todo += takes - len(done)
        refs = ", ".join(k.title() for k in PORTRAIT_CAST if k in shot["cast"]) or "-"
        log(f"shot {cid:<4} {shot['title']:<28} refs: {refs:<14} takes done: {len(done)}/{takes}")
    portraits = [k for k in PORTRAIT_CAST if not (REFS / f"{k.lower()}.png").exists()]
    log(f"\n{len(rows)} clips × {takes} take(s). Still to generate: {len(portraits)} portrait(s), "
        f"{todo} clip(s) = {todo * CLIP_SECONDS} seconds of Veo video.")
    log("Veo bills per second of video — check https://ai.google.dev/gemini-api/docs/pricing before running.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["plan", "portraits", "clips", "film", "all"])
    p.add_argument("--video-model", default="veo-3.1-generate-preview",
                   help="Veo model ID (default: %(default)s; reference portraits need Veo 3.1)")
    p.add_argument("--image-model", default="imagen-4.0-generate-001", help="model for portraits")
    p.add_argument("--resolution", default="720p", choices=["720p", "1080p"])
    p.add_argument("--takes", type=int, default=1, help="versions of each clip to make (sheet suggests 2-3)")
    p.add_argument("--only", help="comma-separated clip IDs to generate, e.g. 03,18a,27")
    p.add_argument("--no-refs", action="store_true", help="don't attach reference portraits")
    p.add_argument("--music", type=Path, help="music file to mix quietly under the film")
    p.add_argument("--music-volume", type=float, default=0.15)
    p.add_argument("--size", default="1920x1080", help="final film frame size (default: %(default)s)")
    p.add_argument("--allow-missing", action="store_true", help="join the film even if some clips are missing")
    args = p.parse_args()

    data = load_data()
    only = {s.strip().zfill(2) if s.strip().isdigit() else s.strip().zfill(3)
            for s in args.only.split(",")} if args.only else None

    if args.step == "plan":
        return plan(data, args.takes)
    if args.step in ("portraits", "clips", "all"):
        api = client()
        if args.step in ("portraits", "all") and not args.no_refs:
            make_portraits(api, data, args.image_model)
        if args.step in ("clips", "all"):
            make_clips(api, data, args.video_model, args.resolution, args.takes, only, not args.no_refs)
    if args.step in ("film", "all"):
        make_film(data, args.music, args.music_volume, args.allow_missing, args.size)


if __name__ == "__main__":
    main()
