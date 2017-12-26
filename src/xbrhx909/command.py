#!/usr/bin/python

"""
A library for controlling a Sony XBR5 television over RS232 serial cable.
"""

from copy import copy
from binascii import a2b_hex as hexencode, b2a_hex as hexdecode
import serial
from time import sleep


class LimitOverError(ValueError):
    """
    Exceeded maximum allowed value
    """
    pass


class LimitUnderError(ValueError):
    """
    Exceeded minimum allowed value
    """
    pass


class CommandCancelled(ValueError):
    """
    Command Cancelled
    """
    pass


class ParseError(ValueError):
    """
    Data Format Error
    """
    pass


class EncodeError(ValueError):
    """
    Can't encode request
    """
    pass


class ResponseError(ValueError):
    """
    Response is garbled/missing
    """
    pass


class SonyXBRHX909(object):
    """
    Control a Sony XBR9 television. May work with other televisions. Does not
    (necessarily) support 100% of XBR9 commands, but the API is actually 
    stolen from a similar, contemporary television--I don't know of any 
    API's specific to this model of television.

    This is also not a complete implementation as there are some features I
    don't care about--like CATV input, volume control, closed captioning, etc.
    """

    command_interval = 0.15  # Sony recommends 0.5, but 0.15 works reliably

    byte0 = '8C'

    byte1 = '00'

    input_groups = {
        'Toggle': '00',
        'TV': '01',
        'Video': '02',
        'Component': '03',
        'HDMI': '04',
        'PC': '05',
    }

    picture_modes = {
        'Vivid': '00',
        'Standard': '01',
        'Custom': '03',
    }

    cinemotion = {
        'Off': '00',
        'Auto1': '02',
        'Auto2': '03',
    }

    wide_modes = {
        'Wide_Zoom': '00',
        'Full': '01',
        'Zoom': '02',
        'Normal': '03',
        'PC_Normal': '05',
        'PC_Full1': '06',
        'PC_Full2': '07',
        'H_Stretch': '09',
    }

    def __init__(self, serial_port='/dev/ttyS0'):
        """
        Creates a new communication instance on the specified serial port.
        You can either pass a string as a reference to the device node (e.g.
        '/dev/ttyS1' for the second serial port) or an integer (e.g. 1).
        """
        # Creates an (active) serial connection.
        self.__conn = serial.Serial(
            port=serial_port, baudrate=9600, bytesize=8, parity='N',
            stopbits=1, timeout=self.command_interval)
        self.c = self.__conn
        
    def _chksum(self, command):
        """
        Calculates and returns a checksum for a passed set of 
        hexadecimal (or decimal) commands. All commands must be in a 
        homogenous format (e.g. cannot be mixed decimal and hexadecimal).
    
        The checksum is returned in the same format as the commands (e.g. 
        either binary or hexadecimal).
        """
        return_binary = True
    
        # Convert all to decimal
        if isinstance(command[0], str):
            command = [int(c, 16) for c in command]
            return_binary = False
    
        # Sum of all commands 
        binsum = sum(command)
    
        # Checksum must be <= 255
        if binsum > 255:
            binsum %= 256
            
        # Return the checksum in the same format as arguments.
        if return_binary:
            return binsum
        else:
            return hex(binsum)[2:4].zfill(2)

    @staticmethod
    def _nsplit(strng):
        n = 2  # Number of characters per group
        return [strng[k:k+n] for k in range(0, len(strng), n)]

    def _cmd(self, command, byte0=None, byte1=None):
        std_cmd = True

        # Set the first two command bytes; use defaults in most cases
        if not byte0:
            std_cmd = False
            byte0 = self.byte0
        if not byte1:
            std_cmd = False
            byte1 = self.byte1

        # Convert first two bytes to hex
        if isinstance(byte0, int):
            byte0 = hex(byte0)[2:].zfill(2)
        if isinstance(byte1, int):
            byte1 = hex(byte1)[2:].zfill(2)

        cmd = [byte0, byte1]

        # Each command has a category code.
        code = command[0]
        if isinstance(code, int):
            code = hex(code)[2:].zfill(2)

        # Each command has a length (of its data) associated with it.
        # N.B. this length INCLUDES the checksum value!
        length = command[1]
        if isinstance(length, int):
            length = hex(length)[2:].zfill(2)
        required_length = int(length, 16)

        # Add the category code and length to the command
        cmd.extend([code, length])

        # The actual command data. Include the checksum for length calculation
        data = command[2:]
        newdata = []
        for d in data:
            if isinstance(d, int):
                d = hex(d)[2:].zfill(2)
            newdata.append(d)
        data = newdata
        data_length = len(data) + 1

        # If issuing TV commands and the lengths don't match, zero-pad value
        if std_cmd and data_length != required_length:
            missing_data_length = required_length - data_length
            zero_pad = ['00' for x in range(missing_data_length)]
            data = zero_pad + data

        # Add the data to the command
        cmd.extend(data)

        # Calculate the checksum and add it to the command
        checksum = self._chksum(cmd)
        cmd.append(checksum)

        # Add a carriage return? Required? Probably not.
        # cmd.append('0D')

        # Hex-encode the command for transmission
        try:
            enccmd = hexencode(''.join(cmd))
        except TypeError:
            raise EncodeError("Cannot encode command: '%s'" % command)

        # Write the command to the serial port connection
        self.__conn.write(enccmd)
        self.__conn.flushOutput()

        # Command responses are always going to be 3 (hex) bytes:
        # 0x70 (header), 0xXX (response code), 0xXX (checksum)
        response = self.__conn.read(6)

        # Wait longer to read the response if nothing was returned
        if len(response) is 0:
            # self.__conn.timeout = 0.1
            response = self.__conn.read(3)
            # self.__conn.timeout = self.command_interval

        # Zero-length responses are an error
        if len(response) is 0:
            raise ResponseError("No response received for command '%s'" % cmd)

        # Decode the hexadecimal response
        dec_response = hexdecode(response)

        # Extract the response (discard header and checksum)
        try:
            response_code = self._nsplit(dec_response)[1]
        except IndexError:
            raise ResponseError("Garbled response: '%s'" % response)

        # Raise exceptions if abnormal termination
        if response_code == '01':
            raise LimitOverError("Value overrun (exceeds maximum limit)")
        elif response_code == '02':
            raise LimitUnderError("Value underrun (below minimum limit)")
        elif response_code == '03':
            raise CommandCancelled("Invalid data/length (command cancelled)")
        elif response_code == '04':
            raise ParseError("Invalid command (parser error)")

        return response_code

    def sircs_command(self, data,  category):
        """Issues a SIRCS command, which require a data and category value.
        The data is usually a large integer and the category a small one (0-2)
        """
        return self._cmd([category, '00', '00'], '81', data)

    def color_temp(self, temp):
        """Changes the set color temperature; valid temps are 00-02
        Does not seem to work.
        """
        return self._cmd(['04', '02', temp], '8C', '10')

    # def picture_mode(self, mode):
    #     """Changes picture mode; valid modes are 00-03.
    #
    #     This doesn't seem to affect picture mode at all. It changes the
    #     CC mode or something. Only '00' has a noticeable effect (?)
    #     """
    #     return self._cmd(['10', '02', mode], '8C', '10')

    def theater_toggle(self):
        """Toggle Theater mode"""
        return self._cmd([3, '00', '00'], '81', 96)

    def _standby_command_on(self):
        """Issue this when powered on to ensure power_on() will work after
        the set is next turned off!"""
        self._cmd(['01', '02', '01'])

    def _standby_command_off(self):
        return self._cmd(['01', '02', '00'])
    
    def power_on(self):
        self._cmd(['00', '02', '01'])

    def power_off(self):
        # self._cmd(['00', '02', '01'], '8C', '00') also works.
        self._standby_command_on()  # ALWAYS do this before powering off!
        return self._cmd(['00', '02', '00'])

    def speaker_on(self):
        """Enables internal speakers"""
        return self._cmd(['36', '03', '01', '01'])

    def speaker_off(self):
        """Disables internal speakers"""
        return self._cmd(['36', '03', '01', '00'])

    def speaker_toggle(self):
        """Toggle internal speakers on/off"""
        return self._cmd(['36', '02', '00'])

    def input_select(self, input_group, input_subgroup, input_unit=None):
        """Generic command for selecting an input"""
        cmd = ['02', input_group, input_subgroup]
        if input_unit:
            cmd.append(input_unit)
        return self._cmd(cmd)

    def input_toggle(self):
        """Toggles through the list of inputs, similar to the television
        remote button."""
        return self.input_select('02', '00')

    def input_tv(self):
        return self.input_select('02', '01')

    def input_video1(self):
        """Shared with Component 1"""
        return self.input_select('03', '02', '01')

    def input_video2(self):
        return self.input_select('03', '02', '02')

    def input_component1(self):
        """Shared with Video 1"""
        return self.input_select('03', '03', '01')

    def input_component2(self):
        return self.input_select('03', '03', '02')

    def input_hdmi1(self):
        return self.input_select('03', '04', '01')

    def input_hdmi2(self):
        return self.input_select('03', '04', '02')

    def input_hdmi3(self):
        return self.input_select('03', '04', '03')

    def input_hdmi4(self):
        return self.input_select('03', '04', '04')

    def input_pc(self):
        """D-sub (analogue) monitor input"""
        return self.input_select('03', '05', '01')

    def program_select_up(self):
        return self._cmd(['04', '03', '00', '00'])

    def program_select_down(self):
        return self._cmd(['04', '03', '00', '01'])

    def picture_toggle(self):
        """Toggles television picture on/off without affecting other
        subunits"""
        return self._cmd(['0D', '02', '00'])

    def picture_off(self):
        """Turns television picture off (but leaves audio on?)"""
        return self._cmd(['0D', '03', '01', '00'])

    def picture_on(self):
        """Opposite to picture_off()"""
        return self._cmd(['0D', '03', '01', '01'])

    def display_toggle(self):
        """Toggles display of picture/input information"""
        return self._cmd(['0F', '02', '00'])

    def picture_mode_toggle(self):
        """Toggles through available picture modes"""
        return self._cmd(['20', '02', '00'])

    def picture_mode(self, mode):
        """
        Explicitly sets a picture mode according to the passed mode
        value. Note that not all modes are supported by all inputs!
        """
        cmd = ['20', '03', '01', mode]
        return self._cmd(cmd)

    def picture_vivid(self):
        """Supported by all inputs."""
        return self.picture_mode(self.picture_modes.get('Vivid'))
    
    def picture_standard(self):
        """Supported by all inputs.."""
        return self.picture_mode(self.picture_modes.get('Standard'))
    
    def picture_custom(self):
        """Supported by all inputs."""
        return self.picture_mode(self.picture_modes.get('Custom'))
    
    def cinemotion_off(self):
        """Turns off CineMotion feature. N.B. if the image contains irregular
        signals or too much noise, this setting is automatically turned off
        even if 'Auto 1' or 'Auto 2' mode is selected."""
        return self._cmd(['2A', '02', self.cinemotion.get('Off')])

    def cinemotion_auto1(self):
        """Provides smoother picture movement than the original film-based
        content. Use this setting for standard use."""
        return self._cmd(['2A', '02', self.cinemotion.get('Auto1')])

    def cinemotion_auto2(self):
        """Provides the original film-based content as-is."""
        return self._cmd(['2A', '02', self.cinemotion.get('Auto2')])

    def wide_toggle(self):
        """Toggles through available wide display modes"""
        return self._cmd(['44', '02', '00'])

    def wide_mode(self, mode):
        """Set an explicit wide view mode"""
        return self._cmd(['44', '03', '01', mode])

    def wide_widezoom(self):
        """Stretches the picture to fill the screen, attempting to preserve
        the original picture."""
        return self.wide_mode(self.wide_modes.get('Wide_Zoom'))

    def wide_full(self):
        """Stretches a 4:3 picture horizontally to fill the screen."""
        return self.wide_mode(self.wide_modes.get('Full'))

    def wide_zoom(self):
        """For old DVD's that are encoded at 4:3 with black bars."""
        return self.wide_mode(self.wide_modes.get('Zoom'))

    def wide_normal(self):
        """Restores normal zoom appearance"""
        return self.wide_mode(self.wide_modes.get('Normal'))

    def wide_pcnormal(self):
        return self.wide_mode(self.wide_modes.get('PC_Normal'))

    def wide_pcfull1(self):
        return self.wide_mode(self.wide_modes.get('PC_Full1'))

    def wide_pcfull2(self):
        return self.wide_mode(self.wide_modes.get('PC_Full2'))

    def wide_hstretch(self):
        return self.wide_mode(self.wide_modes.get('H_Stretch'))

