import os
import sys
import atexit
import socket
import argparse
import readline


def execute(sock: socket.socket, command: str) -> None:
    if not command:
        return
    sock.sendall((command + '\n').encode('utf-8'))
    msg_len = int.from_bytes(sock.recv(4), 'big')
    msg = b''
    while len(msg) < msg_len:
        msg += sock.recv(msg_len - len(msg))
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

    histfile = os.path.join(os.path.expanduser('~'), '.shine_history')
    readline.set_history_length(-1)
    try:
        readline.read_history_file(histfile)
    except FileNotFoundError:
        pass
    atexit.register(readline.write_history_file, histfile)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        try:
            sock.connect(addr)
        except OSError:
            print('failed connecting control socket! try specify.', file=sys.stderr)
            parser.print_usage(file=sys.stderr)
            sys.exit(1)

        if args.command:
            line = ' '.join(args.command)
            readline.add_history(line)
            execute(sock, line)
            return

        print('type "help" for usage', file=sys.stderr)
        while True:
            try:
                execute(sock, input('> '))
            except KeyboardInterrupt:
                print('^C', file=sys.stderr)  # newline
            except EOFError:
                return
            except BrokenPipeError:
                print('Daemon closed connection unexpectedly.', file=sys.stderr)
                return


if __name__ == '__main__':
    main()
