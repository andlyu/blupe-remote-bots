# Run video requests

The off-by-default Settings button requests an emailed sped-up replay. It uses
the adjacent email field, which must contain a valid address when selected.
The choice applies to the next submitted run and is forwarded as the optional
boolean `email_run_video` through the private queue admission path. Unselected
or older clients default to false. It is included in the private submission log,
not public status or conversation data.

The hosted queue notification shows `Sped-up run video requested: Yes` or `No`
next to the entrant's email. This release records the request for the operator;
it does not provision or start automatic video-email delivery.
