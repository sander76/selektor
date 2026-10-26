# selektor

`selektor` lets you browse regular-expression matches in a file from your
terminal. The first match is selected; press `n` to move to the next match
(cycling back to the first), then press Enter to print the selected match to
stdout. Press `q` or Escape to quit without selecting.

```sh
selektor path/to/file 'your-regex'
```

Matches are highlighted in the file view, and the current selection is
emphasized. The file is read as UTF-8.
