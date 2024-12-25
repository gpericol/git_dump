# GitDump 🥷

GitDump is a tool for downloading and reconstructing Git repositories from disclosed `.git` directories. 

This project was inspired by [lijiejie's GitHack](https://github.com/lijiejie/GitHack), a fantastic tool that helped me during a HackTheBox CTF on Christmas night. While using GitHack, I found it incredibly useful, but I wanted to improve certain aspects like adding multi-threading support and making the output less verbose. So, I decided to create GitDump, a tool tailored to my needs.

Special thanks to [lijiejie](https://github.com/lijiejie) for the original inspiration!

---

## Features 🌟

- **Multi-threading**: Accelerate the download process with configurable concurrent threads.
- **Verbosity Levels**: Choose the level of output detail:
  - `0`: Show only successfully downloaded files.
  - `1`: Show all files found in the index.
  - `2`: Include errors for files that could not be downloaded.

---

## Getting Started 🚀

### Prerequisites
Ensure you have Python 3 installed on your system. No additional dependencies are required.

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/gitdump.git
   cd gitdump
   ```

2. Run the script:
   ```bash
   python git_dump.py
   ```

---

## Usage 📖

### Command-Line Arguments:
```
usage: git_dump.py [-h] [-t THREADS] [-v {0,1,2}] url

GitDump: A tool for downloading and reconstructing Git repositories from disclosed .git directories.

positional arguments:
  url                   The base URL of the target Git repository (ending in .git/).

options:
  -h, --help            show this help message and exit
  -t THREADS, --threads THREADS
                        Number of concurrent threads to use (default: 10).
  -v {0,1,2}, --verbosity {0,1,2}
                        Verbosity level (0: only downloaded files, 1: show files found, 2: show errors).
```

### Examples:
```bash
python git_dump.py http://example.com/.git/
```
```bash
python git_dump.py http://example.com/.git/ -t 42 -v 1
```

---

## License 📜

The project is released under the [WTFPL (Do What The F*ck You Want To Public License)](LICENSE), a permissive free software license.

---

## Author 🙌

Created with ❤️ by [gpericol](https://github.com/gpericol).