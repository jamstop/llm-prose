<!-- FIXTURE: a weak draft that buries the interface change ("renames a method,
     adds a parameter") for the interface eval case. The backing diff
     (pr_description_iface.diff) renames a public method and changes its
     signature; a good rewrite must surface that for consumers, not hide it in
     prose. -->

## Refactor user lookup

Renames a method and adds a parameter in `users.py`. Also updates a caller.
