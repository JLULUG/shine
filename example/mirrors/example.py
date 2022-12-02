from shine.helpers import *

# internal name
name = 'example'
on = False

# high priority allows important task to cut in line
# when system resource is not sufficient
priority = 0

# run task using rsync
#run = Rsync(
#    upstream='rsync://example.com/example/',
#    local='/data/'+name,
#    args='--links --hard-links --times --verbose --delete --recursive',
#    exclude='--exclude source/',
#    # timeout in sec
#    timeout=60*60
#)
#run = Rsync2Stage(
#    upstream='rsync://example.com/example/',
#    local='/data/'+name,
#    args='--links --hard-links --times --verbose --delete --recursive',
#    exclude='--exclude source/',
#    firststage='pool/',
#    timeout=60*60
#)
# run task with arbitary program
run = Exit0(System(['dd', 'if=/dev/random', 'count=1024'], timeout=10))

# schedule next task according to interval
next = Interval('15m')
# schedule with crontab spec
#next = Cron('20,40 */7 * * *')
