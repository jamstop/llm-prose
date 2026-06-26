<!-- FIXTURE: a weak draft (pure file/constant enumeration, no Why) for the
     thin-Why eval case. The backing diff (pr_description_nowhy.diff) carries no
     discoverable motivation, so a good rewrite must surface the What/How but
     leave the Why as an explicit author-prompt — never fabricate one. -->

## Update retry settings

Updates `retry.py`. Changes `MAX_RETRIES` from 3 to 5 and `BASE_DELAY` from 0.5 to 1.0.
