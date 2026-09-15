"""Run inside the staging service sandbox; TLS only, no credentials or messages."""
import socket
import ssl


def main():
    context = ssl.create_default_context()
    for host in ('api.paystack.co', 'api.resend.com'):
        try:
            with socket.create_connection((host, 443), timeout=8) as connection:
                with context.wrap_socket(connection, server_hostname=host):
                    print(f'Provider TLS connection verified: {host}', flush=True)
        except Exception:
            raise SystemExit(f'Provider TLS connection failed: {host}; inspect DNS and the service IP allowlist.') from None


if __name__ == '__main__':
    main()
