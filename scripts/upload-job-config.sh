echo $JOB_NAME,$REPO_NAME,$BRANCH_NAME,$TAG_NAME,$REVISION_ID,$COMMIT_SHA,$NEW_VAR,`date '+%Y-%m-%dT%H:%M:%S.00Z'` | gsutil cp - gs://metal-tile-ai-job/${JOB_NAME}.csv