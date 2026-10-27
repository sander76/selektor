# selektor

`selektor` lets you browse regular-expression matches in a file or piped text
from your terminal. The first match is selected; press `n` to move to the next
match (cycling back to the first), then press Enter to print the selected match
to stdout. Press `q` or Escape to quit without selecting.

```sh
selektor path/to/file 'your-regex'
some-command | selektor 'your-regex'

selektor path/to/file 'first-regex' 'second-regex'
some-command | selektor 'first-regex' 'second-regex'
```

Matches from all supplied regexes are browsed in the order they occur in the
input. If matches overlap or begin at the same position, each is selectable.

Matches are highlighted in bright orange in the file view. The current
selection uses the terminal's normal text color on a bright orange background.
Files and piped input are read as UTF-8. The interactive view uses the terminal,
so a controlling terminal must be available when piping input.
