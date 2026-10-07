<div id="top"></div>

<!-- PROJECT LOGO -->
<div align="center">
  <h1 align="center">rymspin</h1>
  <p align="center">Can't decide what to spin next? A command-line tool that picks a random release from the ones a <a href="https://rateyourmusic.com">Rate Your Music</a> user has rated.</p>
  <p>
    <a href="https://github.com/HenestrosaDev/rymspin/actions/workflows/ci.yml">
      <img
        src="https://github.com/HenestrosaDev/rymspin/actions/workflows/ci.yml/badge.svg"
        alt="CI"
      />
    </a>
    <a href="LICENSE">
      <img
        src="https://img.shields.io/badge/license-MIT-lightgray"
        alt="License"
      />
    </a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->

## Table of Contents

- [About the Project](#about-the-project)
  - [Features](#features)
  - [How It Works](#how-it-works)
  - [Project Structure](#project-structure)
  - [Built With](#built-with)
- [Getting Started](#getting-started)
  - [Installing It as a Command](#installing-it-as-a-command)
  - [Setting Up the Project Locally](#setting-up-the-project-locally)
  - [Notes](#notes)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Authors](#authors)
- [License](#license)
- [Support](#support)

<!-- ABOUT THE PROJECT -->

## About the Project

**rymspin** chooses a random entry from the collection of rated releases of any Rate Your Music user (the list at `https://rateyourmusic.com/collection/<user>/r0.5-5.0`) and prints its artist, title, year, rating and link. It's useful to decide what to listen to next from someone's ratings, or from your own.

### Features

- **Any user**: works with the public collection of any RYM user.
- **Rating filter**: limit the choice to a range of ratings, e.g. only the releases rated 4.5 or higher.
- **More filters**: release type (album, EP, single...), year range and the user's own tags.
- **Several picks**: pick any number of different releases at once.
- **Weighted choice**: optionally make higher-rated releases more likely.
- **No repeats**: optionally skip the releases picked in recent runs.
- **Shared picks**: pick a release that two users have both rated in a range, e.g. to find something you both love.
- **Output options**: JSON output, search links for Spotify, YouTube and Bandcamp, the cover, rating date and tags, and opening the picks in the browser.
- **Uniform choice**: every release has the same probability of being picked, whatever page it's on.
- **Few requests**: usually only about two pages are loaded on each run, instead of the whole collection, and never more than `--max-pages`, so it's fast and unlikely to get your IP blocked by RYM.
- **Cache**: loaded pages are saved for 6 hours, so repeated runs are instant and don't even open Chrome.

### How It Works

Rate Your Music is protected by Cloudflare, which blocks plain HTTP requests and detects most headless browsers. The script runs your installed Google Chrome headless with [Playwright](https://playwright.dev/python/), using a regular Chrome user agent, waits for the Cloudflare check to pass and reads the collection pages.

To choose a release, it loads the first page to know how many pages the collection has (25 releases per page), picks a random page and a random position on it, and loads that page. If the position doesn't exist (which can only happen on the last page, as it's usually incomplete), it picks again. This way the choice is uniform without downloading every page.

RYM can only limit the collection by rating, so the other filters (type, year, previous picks) are checked on each picked release: if it doesn't match, the script picks again, loading a new page when needed. This keeps the choice uniform, but a filter that few releases match needs many pages. RYM blocks your IP for a few hours if you load pages too quickly, so the script waits 3 seconds between pages and loads at most 5 pages per run by default (`--max-pages`). Pages saved by earlier runs don't count, so repeated runs find more and more matches.

With `--with OTHER_USER`, it needs to know every release both users rated in the range, so it reads both collections whole instead. It still loads at most `--max-pages` pages per run: if the collections have more, it stops and the next run goes on from the saved pages. A high `--min` keeps the collections small, e.g. `--min 4.5` usually fits in a few pages.

With `--weighted`, a picked release is kept with a probability of its rating divided by 5, so a 5.0 is twice as likely as a 2.5 and ten times as likely as a 0.5.

<!-- PROJECT STRUCTURE -->

### Project Structure

<details>
  <summary>ASCII folder structure</summary>

  ```
  │   .gitignore
  │   .pre-commit-config.yaml
  │   LICENSE
  │   pyproject.toml
  │   README.md
  │   requirements.txt
  │   requirements-dev.txt
  │   rymspin.py
  │
  ├───.github/
  │   └───workflows/
  │           ci.yml
  │
  └───tests/
      │   conftest.py
      │   test_output.py
      │   test_parsing.py
      │   test_sampling.py
      │
      └───fixtures/
              collection.html
  ```
</details>

<!-- BUILT WITH -->

### Built With

- [Playwright for Python](https://playwright.dev/python/) to control Google Chrome and get past the Cloudflare protection.
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) to parse the collection pages.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- GETTING STARTED -->

## Getting Started

### Installing It as a Command

With [pipx](https://pipx.pypa.io/), you can install the script as the `rymspin` command, available from any folder:

```bash
pipx install git+https://github.com/HenestrosaDev/rymspin.git
rymspin <user>
```

`pip install .` from a clone of the repository works too. You still need [Google Chrome](https://www.google.com/chrome/) installed.

### Setting Up the Project Locally

1. Install [Google Chrome](https://www.google.com/chrome/) if you don't have it. The script uses your installed Chrome, so you don't need to run `playwright install`.
2. Clone or download this repository and change the current working directory to its folder by running `cd rymspin`.
3. (Optional but recommended) Create a Python virtual environment in the project root by running `python3 -m venv .venv`. **Python 3.9 or later** is required.
4. (Optional but recommended) Activate the virtual environment:
   ```bash
   # on Windows
   . .venv/Scripts/activate

   # on macOS and Linux
   source .venv/bin/activate
   ```
5. Run `pip install -r requirements.txt` to install the dependencies.
6. Run `python rymspin.py <user>` to pick a random release (see [Usage](#usage)).

### Notes

- Chrome runs in the background without a window. If Cloudflare asks for a verification the headless browser can't pass, the script reopens Chrome with a visible window so you can tick the checkbox. Use `--show` to always show the window.
- The Chrome profile is stored in `~/.rymspin/profile/`, so the Cloudflare session is reused between runs. Delete the folder to start from scratch. Set the `RYMSPIN_HOME` environment variable to use another folder.
- The releases picked are saved in `~/.rymspin/history.json` (the last 1000 per user), which `--no-repeat` uses.
- Loaded pages are saved in `~/.rymspin/cache/` and reused for 6 hours. Use `--refresh` to load them again, e.g. right after rating something new.
- Before the project was renamed to rymspin, its data was stored in `~/.rym-random/`. The first run moves it to `~/.rymspin/`, so you keep your Cloudflare session, cache and history. If you set `RYM_RANDOM_HOME`, rename it to `RYMSPIN_HOME`.
- Earlier versions stored the profile in `.rym_profile/` inside the project folder. You can delete it, or move it to `~/.rymspin/profile/` to keep your Cloudflare session.
- To run the tests, install the development dependencies with `pip install -r requirements-dev.txt` (or `pip install -e ".[dev]"`) and run `pytest`. They use a saved page in `tests/fixtures/`, so they don't connect to RYM. If RYM changes the markup of its collection pages, update the fixture and the tests will show what broke.
- The code is linted and formatted with [Ruff](https://docs.astral.sh/ruff/) and type-checked with [mypy](https://mypy-lang.org/), configured in `pyproject.toml`. Run `pre-commit install` once to check every commit, or `pre-commit run --all-files` to check everything now. GitHub Actions runs the same checks, and the tests on Python 3.9 to 3.14, on every push to `main` and every pull request.
- The collection includes every type of release the user has rated, not only albums, so EPs, singles, compilations, etc. can also be picked.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- USAGE -->

## Usage

```bash
# Pick a random release from all the ones rated by the user
python rymspin.py example_user

# Pick only from the releases rated 4.5 or higher
python rymspin.py example_user --min 4.5

# Pick only from the releases rated between 1 and 2.5
python rymspin.py example_user --min 1 --max 2.5

# Pick 5 different releases
python rymspin.py example_user -n 5

# Pick an EP or a single from the 90s
python rymspin.py example_user --type ep single --from 1990 --to 1999

# Pick a release the user tagged "night" and rated 4 or higher
python rymspin.py example_user --tag night --min 4

# Prefer higher-rated releases and skip the last 50 picks
python rymspin.py example_user --weighted --no-repeat 50

# Show the cover, date and tags, and search links to listen to it
python rymspin.py example_user --details --links

# Pick 3 releases as JSON and open them in the browser
python rymspin.py example_user -n 3 --json --open

# Pick a release that both users rated 4.5 or higher
python rymspin.py example_user --with another_user --min 4.5

# Always show the Chrome window
python rymspin.py example_user --show
```

Example output:

```
Liars - Mess (2014)
Rating: 1.50
https://rateyourmusic.com/release/album/liars/mess/
```

| Option | Description | Default |
| --- | --- | --- |
| `user` | RYM username. | (required) |
| `--min` | Minimum rating. | `0.5` |
| `--max` | Maximum rating. | `5.0` |
| `-n`, `--count` | Number of different releases to pick. | `1` |
| `--type` | Only pick these release types: `album`, `ep`, `single`, `comp`, `mixtape`, `djmix`, `musicvideo`, `video`, `additional`, `bootleg`, `unauth`. | all |
| `--from`, `--to` | Only pick releases from this range of years. Releases without a year are skipped. | all |
| `--tag` | Only pick releases the user tagged with this tag. | all |
| `--weighted` | Make higher-rated releases more likely to be picked. | off |
| `--no-repeat` | Skip the last N releases picked for this user. | off |
| `--max-pages` | Pages to load from RYM at most when filters skip releases. | `5` |
| `--details` | Also show the release type, the date it was rated, the user's tags and the cover. | off |
| `--links` | Also show search links for Spotify, YouTube and Bandcamp. | off |
| `--json` | Print the picks as a JSON list, with every field (and the links with `--links`). | off |
| `--open` | Open the picks on RYM in the web browser. | off |
| `--with` | Only pick releases that this other user also rated within `--min` and `--max`. Both ratings are shown. | off |
| `--show` | Always show the Chrome window. | off |
| `--refresh` | Ignore the pages saved in the last 6 hours and load them again. | off |

Run `python rymspin.py --help` to see all the options.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- TROUBLESHOOTING -->

## Troubleshooting

- **`Couldn't get past the Cloudflare protection.`**: the Cloudflare check didn't pass in 60 seconds. If a Chrome window opens and shows a "Verify you are human" checkbox, tick it while the script waits. If it keeps failing, delete `~/.rymspin/profile/` and try again.
- **`Couldn't find the collection of '<user>'`**: the username is wrong or the collection isn't public. Check that `https://rateyourmusic.com/collection/<user>/r0.5-5.0` opens in your browser.
- **`The collection is empty for that rating range.`**: the user hasn't rated any release in the range of `--min` and `--max`.
- **`... is not a valid rating`**: ratings go from 0.5 to 5.0 in steps of 0.5, and `--min` can't be greater than `--max`.
- **`RYM has temporarily blocked your IP`**: too many pages were loaded in a short time. The block lifts by itself after a few hours; until then, the script can only use the pages it already saved. Use a lower `--max-pages`, or fewer filters, afterwards.
- **`Stopped after loading N pages without finding enough releases`**: the filters match few releases. Run the script again later (the pages loaded so far are saved, so each run searches new ones) or raise `--max-pages` a little.
- **`Loaded N more pages of the two collections, but they have more`**: with `--with`, both collections have to be read whole, which takes several runs if they are big. Run the same command again in a while, or use a higher `--min`.
- **Chrome doesn't open**: Playwright looks for Google Chrome in its default location. Make sure it's installed (Chromium or other browsers aren't used).

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- AUTHORS -->

## Authors

- HenestrosaDev <github@henestrosa.dev> (José Carlos López Henestrosa)

<!-- LICENSE -->

## License

Distributed under the MIT license. See [`LICENSE`](LICENSE) for more information.

<!-- SUPPORT -->

## Support

Would you like to support the project? That's very kind of you! However, I would suggest that you to consider supporting the packages that I've used to build this project first. If you still want to support this particular project, you can go to my Ko-Fi profile by clicking on the button down below!

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/henestrosadev)

<p align="right">(<a href="#top">back to top</a>)</p>
