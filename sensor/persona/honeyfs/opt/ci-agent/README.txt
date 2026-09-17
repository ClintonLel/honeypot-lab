ci-agent
========

In-house build agent. Polls the coordinator for jobs, checks out sources from
git.build.internal, runs the job script in /srv/build/workspace/<job-id> and
moves the results to /srv/build/artifacts. artifact-sync.timer uploads them.

Layout
  bin/ci-agent      launcher
  etc/agent.ini     configuration (managed, do not edit by hand)
  venv/             python virtual environment
  VERSION           installed release

Service
  systemctl status ci-agent
  journalctl -u ci-agent
