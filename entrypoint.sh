#!/bin/sh
chown -R appuser:appuser /app/data
exec python3 -c "
import os, pwd, sys
pw = pwd.getpwnam('appuser')
os.setgroups([pw.pw_gid])
os.setgid(pw.pw_gid)
os.setuid(pw.pw_uid)
os.execvp(sys.argv[1], sys.argv[1:])
" "$@"
