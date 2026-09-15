# Log method and path, without the query string, referer, or authentication data.
# In particular, Meta's hub.verify_token must not enter the system journal.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s'
