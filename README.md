# AI-Video

Prompt packs for making short realistic films with AI video apps (Google Veo, Kling, etc.).

## David and Goliath

32 shots (~8 s each, about 4–5 minutes total) with King James Bible dialogue from 1 Samuel 17.
Shot 18's long line is split into two clips (18a, 18b), so there are 33 clips.

### Make the whole film automatically (Google Veo)

`make_film.py` creates David and Goliath reference portraits, generates every
clip with Veo (attaching the portraits so faces stay the same), and joins the
clips into `david-and-goliath/output/david-and-goliath.mp4`.

You need Python 3, ffmpeg, and a Gemini API key from https://aistudio.google.com/apikey
with billing on. Veo is billed per second of video: the full film is about
264 seconds of generated video per take, so check the
[pricing page](https://ai.google.dev/gemini-api/docs/pricing) first.

```bash
pip install google-genai
```

```bash
export GEMINI_API_KEY=your-key-here
```

```bash
python3 david-and-goliath/make_film.py plan
```

```bash
python3 david-and-goliath/make_film.py all
```

- `plan` costs nothing: it lists every clip and what is left to generate.
- Re-running is safe. Finished clips are skipped, so an interrupted run picks up where it stopped.
- `--takes 3` makes three versions of each clip (`shot-03.mp4`, `shot-03.take2.mp4`, …).
  To use a different take, copy it over `shot-03.mp4` and run `make_film.py film` again.
- `--only 03,18a,27` (re)generates just those clips. Delete a clip's file first to replace it.
- `--music song.mp3` mixes music quietly under the film when joining.
- If Veo refuses a narrated battle shot, the script retries it as the soldiers
  watching (the sheet's advice). Anything still refused is listed in `output/failed.json`.
- `--video-model` and `--image-model` let you switch models (default: `veo-3.1-generate-preview`
  and `imagen-4.0-generate-001`). Reference portraits need a Veo 3.1 model.

### Or make it by hand

| File | What it is |
| --- | --- |
| [`david-and-goliath/ALL_PROMPTS.md`](david-and-goliath/ALL_PROMPTS.md) | Every clip's full prompt, in order, ready to copy |
| `david-and-goliath/clips/shot-NN.txt` | The same prompts, one file per clip |
| `david-and-goliath/shots.json` | Source of truth: style, characters and shots |
| `david-and-goliath/build_prompts.py` | Rebuilds the prompts after you edit `shots.json` |
| `david-and-goliath/make_film.py` | Generates the clips with Veo and joins them into the film |
| `david-and-goliath/David_and_Goliath_AI_Video_Prompts.pdf` | The original prompt sheet |

Each prompt is already assembled the way the sheet says: the STYLE block, then the
description of every character on the shot's cast line (plus the narrator for
narrated shots), then the shot description and its spoken line. Paste one whole
prompt per clip — don't change the character wording, or faces will drift.

Tips from the sheet:

- If the app accepts reference images, make one portrait of David and one of Goliath
  first and attach them to every clip.
- Make 2–3 versions of each clip and keep the best.
- If the app refuses a battle shot, cut to the soldiers' faces watching instead.
- Join the clips in order in CapCut or InShot and add music there.

To change a shot or a character, edit `shots.json` and run:

```bash
python3 david-and-goliath/build_prompts.py
```
