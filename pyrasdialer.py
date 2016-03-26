import os
import argparse
import ConfigParser
import time
import random
import subprocess
import tempfile
import uuid


__author__ = "pyface.net"
__version__ = "0.1"
__license__ = "MIT License"

RASDIAL_EXE = os.path.expandvars("%SystemRoot%\\System32\\rasdial.exe")
TEMP_PBK_FILE = tempfile.gettempdir() + os.path.sep + "pyrasdialer.pbk"
VPN_SUFFIX = "_pyrasdialer"


def log(message):
    print message


class EqualsSpaceRemover:
    output_file = None

    def __init__(self, new_output_file):
        self.output_file = new_output_file

    def write(self, what):
        self.output_file.write(what.replace(" = ", "="))


class VPNConnection:
    def __init__(self):
        self.server_list = []
        self.phone_book_file = None
        self.phone_book_entry = None
        self.phone_book = None
        self.username = ""
        self.password = ""
        self.is_connected = False
        pass

    def parse_config(self, config):
        if config.has_option("default", "server_list"):
            self.server_list = [server.strip() for server in config.get("default", "server_list").split(',')]
        if config.has_option("default", "username"):
            self.username = config.get("default", "username")
        if config.has_option("default", "password"):
            self.password = config.get("default", "password")
        if config.has_option("default", "ras_pbk_file"):
            self.phone_book_file = os.path.expandvars(config.get("default", "ras_pbk_file"))
        if config.has_option("default", "vpn_connection_name"):
            self.phone_book_entry = config.get("default", "vpn_connection_name")

        self.phone_book = ConfigParser.ConfigParser()
        self.phone_book.optionxform = str
        self.phone_book.read(self.phone_book_file)

        if not self.phone_book.has_section(self.phone_book_entry):
            self.phone_book = None
            return False
        else:
            items = self.phone_book.items(self.phone_book_entry)
            self.phone_book.remove_section(self.phone_book_entry)
            self.phone_book.add_section(self.phone_book_entry + VPN_SUFFIX)
            for item in items:
                self.phone_book.set(self.phone_book_entry + VPN_SUFFIX, item[0], item[1])
            self.phone_book_entry += VPN_SUFFIX
            vpn_guid = str(uuid.uuid1()).replace("-", "").upper()
            self.phone_book.set(self.phone_book_entry, "Guid", vpn_guid)
        return True

    def do_disconnect(self):
        try:
            subprocess.check_call([RASDIAL_EXE, self.phone_book_entry, "/DISCONNECT"])
            self.is_connected = False
            log("[MSG]: disconnected from VPN successfully")
        except subprocess.CalledProcessError as err:
            log("[ERROR]: failed to disconnect to VPN with error: %d" % err.returncode)

    def do_connect(self):
        self.check_connection()
        if self.is_connected:
            return
        try:
            self._randomize_server()
            log("[MSG]: attempting to connect to VPN ...")
            proc_args = [RASDIAL_EXE, self.phone_book_entry, self.username, self.password,
                         "/PHONEBOOK:" + TEMP_PBK_FILE]
            print proc_args
            subprocess.check_call(proc_args)
            self.is_connected = True
            log("[MSG]: connected to VPN successfully")
        except subprocess.CalledProcessError as err:
            log("[ERROR]: failed to connect to VPN with error: %d" % err.returncode)

    def check_connection(self):
        try:
            rasdial_output = subprocess.check_output([RASDIAL_EXE])
            if "No connections" in rasdial_output:
                self.is_connected = False
            elif self.phone_book_entry in rasdial_output:
                self.is_connected = True
            else:
                self.is_connected = False
        except subprocess.CalledProcessError as err:
            log("[ERROR]: failed to check VPN connection with error: %d" % err.returncode)
        return self.is_connected

    def _randomize_server(self):
        if len(self.server_list) >= 0:
            index = random.randint(0, len(self.server_list) - 1)
            new_server = self.server_list[index].strip()
            self.phone_book.set(self.phone_book_entry, "PhoneNumber", new_server)
            log("[MSG]: Setting VPN server to... %s " % new_server)
        with open(TEMP_PBK_FILE, 'w+') as outfile:
            self.phone_book.write(EqualsSpaceRemover(outfile))
            outfile.close()


def get_connection_options(config):
    reconnect_if_dropped = False
    disconnect_timer = 0
    if config.has_option("default", "reconnect_if_dropped"):
        reconnect_if_dropped = config.getboolean("default", "reconnect_if_dropped")
    if config.has_option("default", "disconnect_timer"):
        disconnect_timer = config.getint("default", "disconnect_timer")
    return reconnect_if_dropped, disconnect_timer


def get_args():
    default_config_filename = "pyrasdialer.ini"
    program = os.path.basename(__file__).split('.')[0]
    arg_parser = argparse.ArgumentParser(prog=program, version=__version__,
                                         description="A wrapper around rasdial.exe to randomize server, "
                                                     "connect, and monitor a VPN connection")

    arg_parser.add_argument('-c', '-config', dest='configFile',
                            default=os.path.join(os.getcwd(), default_config_filename),
                            help="path to configuration file to use "
                            "(default = ./" + default_config_filename + ")")

    args = arg_parser.parse_args()

    if not os.path.isfile(args.configFile):
        log("[ERROR]: config (%s) does not exist" % args.configFile)
        return None
    return args


def main():
    args = get_args()
    vpn_conn = VPNConnection()
    if args:
        config = ConfigParser.ConfigParser()
        config.read(args.configFile)
        if not vpn_conn.parse_config(config):
            print("[ERROR]: failed to parse VPN config")
        else:
            reconnect_if_dropped, disconnect_timer = get_connection_options(config)
            time_count = 0
            vpn_conn.do_connect()
            while 0 < disconnect_timer or reconnect_if_dropped:
                vpn_conn.check_connection()
                if not vpn_conn.is_connected:
                    log("[WARN]: VPN is not connected...")
                    if reconnect_if_dropped:
                        log("[MSG]: Attempting to reconnect...")
                        vpn_conn.do_connect()
                    else:
                        break
                time.sleep(60)
                time_count += 1
                if disconnect_timer and time_count >= disconnect_timer:
                    log("[MSG]: Disconnect timer reached... disconnecting...")
                    vpn_conn.do_disconnect()
                    break


if __name__ == "__main__":
    random.seed()
    main()
