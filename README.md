# AI-Video

Prompt packs for making short realistic films with AI video apps (Google Veo, Kling, etc.).

## David and Goliath

32 shots (~8 s each, about 4–5 minutes total) with King James Bible dialogue from 1 Samuel 17.

| File | What it is |
| --- | --- |
| [`david-and-goliath/ALL_PROMPTS.md`](david-and-goliath/ALL_PROMPTS.md) | Every clip's full prompt, in order, ready to copy |
| `david-and-goliath/clips/shot-NN.txt` | The same prompts, one file per clip |
| `david-and-goliath/shots.json` | Source of truth: style, characters and shots |
| `david-and-goliath/build_prompts.py` | Rebuilds the prompts after you edit `shots.json` |
| `david-and-goliath/David_and_Goliath_AI_Video_Prompts.pdf` | The original prompt sheet |

Each prompt is already assembled the way the sheet says: the STYLE block, then the
description of every character on the shot's cast line (plus the narrator for
narrated shots), then the shot description and its spoken line. Paste one whole
prompt per clip — don't change the character wording, or faces will drift.

Tips from the sheet:

- If the app accepts reference images, make one portrait of David and one of Goliath
  first and attach them to every clip.
- Make 2–3 versions of each clip and keep the best.
- Shot 18 has a long line: use a 10-second clip or split it in two.
- If the app refuses a battle shot, cut to the soldiers' faces watching instead.
- Join the clips in order in CapCut or InShot and add music there.

To change a shot or a character, edit `shots.json` and run:

```bash
python3 david-and-goliath/build_prompts.py
```
