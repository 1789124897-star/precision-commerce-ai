warning: in the working copy of '.env.example', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '.gitignore', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'README.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'app/api/routes/analysis.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'app/services/analysis.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'app/services/scraper.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'app/services/script_generator.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'app/services/video_composer.py', LF will be replaced by CRLF the next time Git touches it
 .env.example                     |  26 [32m++[m[31m-[m
 .gitignore                       |   4 [32m+[m
 README.md                        |  62 [32m+++[m[31m---[m
 app/api/routes/analysis.py       |   2 [32m+[m
 app/config/scraper_config.yaml   |   6 [32m+[m[31m-[m
 app/services/analysis.py         |  92 [32m+++++[m[31m----[m
 app/services/image_gen.py        |  85 [32m++++[m[31m----[m
 app/services/scraper.py          |   2 [32m+[m[31m-[m
 app/services/script_generator.py |   5 [32m+[m
 app/services/seedance_service.py | 410 [32m+++++++++++++++++++++++++++++++++++++++[m
 app/services/tts_service.py      |  15 [32m+[m[31m-[m
 app/services/video_composer.py   |   9 [32m+[m[31m-[m
 app/tasks/analysis.py            |   4 [32m+[m[31m-[m
 app/tasks/image_gen.py           |   4 [32m+[m[31m-[m
 app/tasks/script_gen.py          |   8 [32m+[m[31m-[m
 app/tasks/strategy.py            |   4 [32m+[m[31m-[m
 app/tasks/tts_gen.py             |   7 [32m+[m[31m-[m
 app/tasks/video.py               |   7 [32m+[m[31m-[m
 docker-compose.yml               |   4 [32m+[m[31m-[m
 19 files changed, 595 insertions(+), 161 deletions(-)
