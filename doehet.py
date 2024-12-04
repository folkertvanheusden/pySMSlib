#! /usr/bin/env python3

# This code was written by Folkert van Heusden <mail@vanheusden.com> for NURDspace.
# Released under the MIT license.

from dateutil.parser import parse
import serial
import sys
import time


class sms_modem:
    def __init__(self, port):
        self.handle = serial.Serial(port, timeout=2)
        self.handle.reset_input_buffer()

    def _send_receive(self, command):
        self.handle.write('\r\n'.encode('ascii'))
        self.handle.write((command + '\r\n').encode('ascii'))

        response = []
        line = ''
        while True:
            c = self.handle.read(1)
            if c == None:  # time out
                return None

            c = int.from_bytes(c)
            if c == 10 or c == 13:
                if len(line) > 0:
                    response.append(line)
                    if line == 'OK' or line == 'ERROR':
                        break
                    line = ''
            else:
                line += chr(c)

        return response

    def _log(self, what, context):
        print(what, file=sys.stderr)
        print(context, file=sys.stderr)

    def _batch(self, commands):
        for command in commands:
            print(f'Invoking: {command}')
            rc = self._send_receive(command[0])
            if rc == None or rc[-1] == 'ERROR':
                if command[1]:
                    self._log(f'{command} failed - expected', rc)
                else:
                    self._log(f'{command} failed', rc)
                    return False
            if rc != None:
                print(f'Returned: {rc[-1]}')

        return True

    def begin(self, pin):
        self.handle.write(chr(26).encode('ascii'))  # ^Z to end any pending message

        return self._batch((
            ('ATZ', False),  # reset modem
            ('ATE1', False),  # local echo on
            ('AT+CMEE=0', False),  # disable extended errors
            # modems sometimes say error when the pin was already entered
            (f'AT+CPIN="{pin}"', True),  # set pin
            ('AT+CMGF=1', False),  # go to SMS mode
            )
                           )

    def poll_storage(self, id_, delete_after_read):
        cmd = f'AT+CPMS="{id_}"'
        rc = self._send_receive(cmd)
        if rc == None or rc[-1] == 'ERROR':
            self._log(f'{cmd} failed', rc)
            return None

        if rc[1][0:6] != '+CPMS:':
            self._log(f'{cmd} failed: unexpected response', rc)
            return None

        parameters = rc[1].split()
        n_messages = int(parameters[1].split(',')[0])
        print(f'Has {n_messages} messages')

        messages = []
        for i in range(1, n_messages + 1):
            print(f'Fetching message {i}')

            # get
            cmd = f'AT+CMGR={i}'
            rc = self._send_receive(cmd)
            if rc == None or rc[-1] == 'ERROR':
                self._log(f'{cmd} failed', rc)
                break

            # +CMGR: "REC READ","+31637556130",,"24/11/23,21:03:26+04"
            parts = rc[1].split(',')
            text = []
            for line in rc[2:-1]:
                text.append(line)
            date_str = '20' + parts[3][1:] + ' ' + parts[4][:8]
            message = { 'caller': parts[1], 'ts': parse(date_str), 'text': text }
            messages.append(message)

            # delete
            if delete_after_read:
                cmd = f'AT+CMGD={i}'
                rc = self._send_receive(cmd)
                if rc == None or rc[-1] == 'ERROR':
                    self._log(f'{cmd} failed', rc)
                    break

        return messages

    def transmit_message(self, victim, text):
        # special case :-(
        cmd = f'AT+CMGS="{victim}"\r\n'
        self.handle.write(cmd.encode('ascii'))

        for line in text:
            if chr(26) in line:  # prevent ^Z codes (as that would end the msg)
                continue
            buffer = ''
            while True:
                # wait for '> '
                c = self.handle.read(1)
                if c == None:  # time out
                    return False
                buffer += chr(int.from_bytes(c))
                if buffer[-4:] == '\r\n> ':
                    break

            self.handle.write((line + '\r\n').encode('ascii'))

        self.handle.write(chr(26).encode('ascii'))  # ^Z to end the message

        rc = ''
        while True:
            c = self.handle.read(1)
            if c == None:
                return False

            rc += chr(int.from_bytes(c))
            if '\r\nOK\r\n' in rc:
                return True
            if '\r\nERROR\r\n' in rc:
                return False

        return False


port = '/dev/ttyACM3'
pin = '0000'

modem = sms_modem(port)
print(modem.begin(pin))
print(modem.poll_storage('SM', False))  # SM=sim memory
#print(modem.transmit_message('+31641278122', ('Dit is een test.', 'Poep is vies.', 'Absoluut.')))
