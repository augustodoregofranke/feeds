# feeds

Personal RSS feeds, rebuilt daily by GitHub Actions and served at
https://feeds.augustodoregofranke.com

- `jobs.xml`: GPU / ML-systems and early-career jobs that are remote-worldwide
  or in Brazil, pulled straight from company job boards (Greenhouse, Ashby,
  Workday). Edit `COMPANIES` and the filters at the top of `jobs_feed.py`.


Run locally: `python3 jobs_feed.py --report`
