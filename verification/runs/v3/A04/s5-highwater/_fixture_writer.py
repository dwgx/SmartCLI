import sys
n = int(sys.argv[1])
payload = bytes((i * 7 + 11) % 251 for i in range(n))
sys.stdout.buffer.write(payload)
sys.stdout.buffer.flush()
sys.stderr.write('WROTE %d %s\n' % (n, __import__('hashlib').sha256(payload).hexdigest()))
sys.stderr.flush()
