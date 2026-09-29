sudo systemctl status ci-agent
sudo journalctl -u ci-agent -n 50 --no-pager
df -h /srv
sudo du -sh /srv/build/cache/*
sudo systemctl list-timers artifact-sync.timer
ls -la /srv/build/artifacts/
cat /opt/ci-agent/VERSION
sudo apt update
apt list --upgradable
sudo apt upgrade
sudo systemctl restart ci-agent
sudo tail -n 20 /var/log/ci-agent/agent.log
free -m
uptime
sudo find /srv/build/workspace -maxdepth 1 -type d -mtime +7
vi runbook.txt
exit
