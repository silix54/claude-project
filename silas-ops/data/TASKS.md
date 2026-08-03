# Tasks (superseded)

The dashboard no longer reads this file — tasks live in Google Tasks now
(src/gtasks.py), read/write through the app itself or the Google Tasks app.
This file is kept only as a worked example of the `@tag !quadrant ~estimate`
convention, which gtasks.py parses out of a task's notes field the same way.

    - [ ] text @tag !quadrant ~estimate due:YYYY-MM-DD

  @tag        school work career faith fitness admin
  !quadrant   !now   urgent and important
              !plan  important, not urgent  <- most of what matters lives here
              !quick urgent, not important
              !drop  neither
  ~est        ~45m or ~2h
  due:        ISO date

## Open

- [ ] Confirm DND hiring mechanism, student status for bridging @career !now ~30m due:2026-08-08
- [ ] Pull all six syllabi into config/term.yaml @school !now ~45m due:2026-09-11
- [ ] Set a target date for French BBB @career !plan ~20m
- [ ] Register for the July 2027 70.3 once dates post @fitness !plan ~15m
- [ ] Decide graduation timing, minor or no minor @school !plan ~1h
- [ ] Add reserve weekends to config/term.yaml @admin !quick ~10m

## Done

- [x] Submit CSIS student applications @career
