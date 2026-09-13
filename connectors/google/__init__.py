"""connectors/google/ — ONE Google identity for the whole engine (V2-684).

Gmail, Calendar, Meet, Drive, Photos and YouTube are six doors into the SAME Google account, and the
engine had grown six copies of the same OAuth app question — `EMAIL_GMAIL_CLIENT_ID`,
`VIDEO_YOUTUBE_CLIENT_ID`, `PHOTOS_GOOGLE_PHOTOS_CLIENT_ID`, `FILES_GDRIVE_CLIENT_ID`,
`CALENDAR_GOOGLE_CLIENT_ID` — each of which the operator had to answer separately with the same value.

This package holds the answer ONCE. `app.py` is where Zaelar's own OAuth client lives; `services.py`
is the map of which Google service this build can reach, who fronts it, and whether it has a surface.

It is a LEAF: nothing here imports another connector, because everything else imports this.
"""
