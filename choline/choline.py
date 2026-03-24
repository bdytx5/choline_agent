import sys
from choline.commands import repeat, code, status, init, stream, launch, sync, kill, transer_data, bid, ui, ssh
import os

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

def main():
    print("DEBUG: choline main() starting", flush=True)
    command = sys.argv[1] if len(sys.argv) > 1 else None
    if command == 'ssh':
        ssh.run()
    elif command == 'code':
        code.run()
    elif command == 'status':
        status.run()
    elif command == 'init':
        init.run()
    elif command == 'stream':
        stream.run()
    elif command == 'kill':
        kill.run()        
    elif command == 'launch':
        if os.geteuid() != 0:
            print("Choline launch must be run as root!")
            sys.exit(1)

        if len(sys.argv) > 2:
            launch.run(sys.argv[2]) # when called by bid 
        else:
            launch.run()

    elif command == 'bid':
        if os.geteuid() != 0:
            print("Choline launch must be run as root!")
            sys.exit(1)
        bid.run()

    elif command == 'reinit':
        init.run_reinit()
    elif command == 'sync':
        sync.run()
    elif command == 'ui':
        ui.run()
    # elif command == 'spot':
    #     transer_data.run("byyoung3@34.28.218.185")
    else:
        print("Unknown command")

if __name__ == "__main__":
    main()
