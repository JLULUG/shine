import os
import sys
import socket
import argparse
import readline


def execute(sock: socket.socket, command: str) -> None:
    if not command:
        return
    sock.sendall((command+'\n').encode('utf-8'))
    msg_len = int.from_bytes(sock.recv(4), 'big')
    msg = b''
    while len(msg) < msg_len:
        msg += sock.recv(msg_len-len(msg))
    print(msg.decode('utf-8', errors='ignore'))


def main() -> None:
    """simple control socket client"""
    parser = argparse.ArgumentParser(prog='shine', add_help=False)
    parser.add_argument('-s', '--socket')
    parser.add_argument('command', nargs='*')
    args = parser.parse_args()
    if args.socket:
        addr = args.socket
    elif os.path.exists('/run/shine/shined.sock'):
        addr = '/run/shine/shined.sock'
    elif os.path.exists('shined.sock'):
        addr = 'shined.sock'
    else:
        print('cannot find control socket! please specify.', file=sys.stderr)
        parser.print_usage(file=sys.stderr)
        sys.exit(1)

    readline.set_history_length(1000)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        try:
            sock.connect(addr)
        except OSError:
            print('failed connecting control socket! try specify.', file=sys.stderr)
            parser.print_usage(file=sys.stderr)
            sys.exit(1)
        if args.command:
            execute(sock, ' '.join(args.command))
            return
        print('type "help" for usage', file=sys.stderr)
        while True:
            try:
                execute(sock, input('> '))
            except (EOFError, KeyboardInterrupt):
                return


if __name__ == '__main__':
    main()
