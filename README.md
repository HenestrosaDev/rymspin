<div id="top"></div>

<!-- PROJECT LOGO -->
<div align="center">
  <h1 align="center">RYM Random Rated Album</h1>
  <p align="center">A command-line script that picks a random release from all the ones a <a href="https://rateyourmusic.com">Rate Your Music</a> user has rated.</p>
  <p>
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
  - [Setting Up the Project Locally](#setting-up-the-project-locally)
  - [Notes](#notes)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Authors](#authors)
- [License](#license)
- [Support](#support)

<!-- ABOUT THE PROJECT -->

## About the Project

**RYM Random Rated Album** chooses a random entry from the collection of rated releases of any Rate Your Music user (the list at `https://rateyourmusic.com/collection/<user>/r0.5-5.0`) and prints its artist, title, year, rating and link. It's useful to decide what to listen to next from someone's ratings, or from your own.

### Features

- **Any user**: works with the public collection of any RYM user.
- **Rating filter**: limit the choice to a range of ratings, e.g. only the releases rated 4.5 or higher.
- **Uniform choice**: every release has the same probability of being picked, whatever page it's on.
- **Few requests**: only about two pages are loaded on each run, instead of the whole collection, so it's fast and unlikely to get your IP blocked by RYM.

### How It Works

Rate Your Music is protected by Cloudflare, which blocks plain HTTP requests and detects most headless browsers. The script runs your installed Google Chrome headless with [Playwright](https://playwright.dev/python/), using a regular Chrome user agent, waits for the Cloudflare check to pass and reads the collection pages.

To choose a release, it loads the first page to know how many pages the collection has (25 releases per page), picks a random page and a random position on it, and loads that page. If the position doesn't exist (which can only happen on the last page, as it's usually incomplete), it picks again. This way the choice is uniform without downloading every page.

<!-- PROJECT STRUCTURE -->

### Project Structure

<details>
  <summary>ASCII folder structure</summary>

  ```
  │   .gitignore
  │   LICENSE
  │   README.md
  │   requirements.txt
  │   requirements-dev.txt
  │   rym_random.py
  │
  ├───tests/
  │   │   test_parsing.py
  │   │
  │   └───fixtures/
  │           collection.html
  │
  └───.rym_profile/ (Chrome profile with the Cloudflare session, created on the first run)
  ```
</details>

<!-- BUILT WITH -->

### Built With

- [Playwright for Python](https://playwright.dev/python/) to control Google Chrome and get past the Cloudflare protection.
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) to parse the collection pages.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- GETTING STARTED -->

## Getting Started

### Setting Up the Project Locally

1. Install [Google Chrome](https://www.google.com/chrome/) if you don't have it. The script uses your installed Chrome, so you don't need to run `playwright install`.
2. Clone or download this repository and change the current working directory to its folder by running `cd rym_random_rated_album`.
3. (Optional but recommended) Create a Python virtual environment in the project root by running `python3 -m venv .venv`. **Python 3.9 or later** is required.
4. (Optional but recommended) Activate the virtual environment:
   ```bash
   # on Windows
   . .venv/Scripts/activate

   # on macOS and Linux
   source .venv/bin/activate
   ```
5. Run `pip install -r requirements.txt` to install the dependencies.
6. Run `python rym_random.py <user>` to pick a random release (see [Usage](#usage)).

### Notes

- Chrome runs in the background without a window. If Cloudflare asks for a verification the headless browser can't pass, the script reopens Chrome with a visible window so you can tick the checkbox. Use `--show` to always show the window.
- The Chrome profile is stored in `.rym_profile/`, so the Cloudflare session is reused between runs. Delete the folder to start from scratch.
- To run the tests, install the development dependencies with `pip install -r requirements-dev.txt` and run `pytest`. They use a saved page in `tests/fixtures/`, so they don't connect to RYM. If RYM changes the markup of its collection pages, update the fixture and the tests will show what broke.
- The collection includes every type of release the user has rated, not only albums, so EPs, singles, compilations, etc. can also be picked.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- USAGE -->

## Usage

```bash
# Pick a random release from all the ones rated by the user
python rym_random.py example_user

# Pick only from the releases rated 4.5 or higher
python rym_random.py example_user --min 4.5

# Pick only from the releases rated between 1 and 2.5
python rym_random.py example_user --min 1 --max 2.5

# Always show the Chrome window
python rym_random.py example_user --show
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
| `--show` | Always show the Chrome window. | off |

Run `python rym_random.py --help` to see all the options.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- TROUBLESHOOTING -->

## Troubleshooting

- **`Couldn't get past the Cloudflare protection.`**: the Cloudflare check didn't pass in 60 seconds. If a Chrome window opens and shows a "Verify you are human" checkbox, tick it while the script waits. If it keeps failing, delete `.rym_profile/` and try again.
- **`Couldn't find the collection of '<user>'`**: the username is wrong or the collection isn't public. Check that `https://rateyourmusic.com/collection/<user>/r0.5-5.0` opens in your browser.
- **`The collection is empty for that rating range.`**: the user hasn't rated any release in the range of `--min` and `--max`.
- **`... is not a valid rating`**: ratings go from 0.5 to 5.0 in steps of 0.5, and `--min` can't be greater than `--max`.
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
