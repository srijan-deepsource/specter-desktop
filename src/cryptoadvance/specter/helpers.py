import collections, copy, hashlib, json, logging, os, six, subprocess, sys
from collections import OrderedDict


try:
    collectionsAbc = collections.abc
except:
    collectionsAbc = collections

logger = logging.getLogger(__name__)
def alias(name):
    name = name.replace(" ", "_")
    return "".join(x for x in name if x.isalnum() or x=="_").lower()

def deep_update(d, u):
    for k, v in six.iteritems(u):
        dv = d.get(k, {})
        if not isinstance(dv, collectionsAbc.Mapping):
            d[k] = v
        elif isinstance(v, collectionsAbc.Mapping):
            d[k] = deep_update(dv, v)
        else:
            d[k] = v
    return d

def load_jsons(folder, key=None):
    files = [f for f in os.listdir(folder) if f.endswith(".json")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(folder, x)))
    dd = OrderedDict()
    for fname in files:
        with open(os.path.join(folder, fname)) as f:
            d = json.loads(f.read())
        if key is None:
            dd[fname[:-5]] = d
        else:
            d["fullpath"] = os.path.join(folder, fname)
            d["alias"] = fname[:-5]
            dd[d[key]] = d
    return dd

BASE58_ALPHABET = b'123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def double_sha256(s):
    return hashlib.sha256(hashlib.sha256(s).digest()).digest()

def hash160(d):
    return hashlib.new('ripemd160', hashlib.sha256(d).digest()).digest()

def encode_base58(s):
    # determine how many 0 bytes (b'\x00') s starts with
    count = 0
    for c in s:
        if c == 0:
            count += 1
        else:
            break
    prefix = b'1' * count
    # convert from binary to hex, then hex to integer
    num = int.from_bytes(s, 'big')
    result = bytearray()
    while num > 0:
        num, mod = divmod(num, 58)
        result.insert(0, BASE58_ALPHABET[mod])

    return prefix + bytes(result)

def encode_base58_checksum(s):
    return encode_base58(s + double_sha256(s)[:4]).decode('ascii')

def decode_base58(s, num_bytes=82, strip_leading_zeros=False):
    num = 0
    for c in s.encode('ascii'):
        num *= 58
        num += BASE58_ALPHABET.index(c)
    combined = num.to_bytes(num_bytes, byteorder='big')
    if strip_leading_zeros:
        while combined[0] == 0:
            combined = combined[1:]
    checksum = combined[-4:]
    if double_sha256(combined[:-4])[:4] != checksum:
        raise ValueError('bad address: {} {}'.format(
            checksum, double_sha256(combined)[:4]))
    return combined[:-4]

def convert_xpub_prefix(xpub, prefix_bytes):
    # Update xpub to specified prefix and re-encode
    b = decode_base58(xpub)
    return encode_base58_checksum(prefix_bytes + b[4:])

def get_xpub_fingerprint(xpub):
    b = decode_base58(xpub)
    return hash160(b[-33:])[:4]

def which(program):
    ''' mimics the "which" command in bash but even for stuff not on the path.
        Also has implicit pyinstaller support 
        Place your executables like --add-binary '.env/bin/hwi:.'
        ... and they will be found.
        returns a full path of the executable and if a full path is passed,
        it will simply return it if found and executable
        will raise an Exception if not found
    '''
    
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    if getattr(sys, 'frozen', False):
        # Best understood with the snippet below this section:
        # https://pyinstaller.readthedocs.io/en/v3.3.1/runtime-information.html#using-sys-executable-and-sys-argv-0
        exec_location = os.path.join(sys._MEIPASS, program)
        if is_exe(exec_location):
            logger.info("Found %s executable in %s" % (program, exec_location))
            return exec_location

    fpath, program_name = os.path.split(program)
    if fpath:
        if is_exe(program):
            logger.info("Found %s executable in %s" % (program, program))
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                logger.info("Found %s executable in %s" % (program, path))
                return exe_file
    raise Exception("Couldn't find executable %s" % program)

# should work in all python versions
def run_shell(cmd):
    """
    Runs a shell command. 
    Example: run(["ls", "-a"])
    Returns: dict({"code": returncode, "out": stdout, "err": stderr})
    """
    try:
        proc = subprocess.Popen(cmd,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
        )
        stdout, stderr = proc.communicate()
        return { "code": proc.returncode, "out": stdout, "err": stderr }
    except:
        return { "code": 0xf00dbabe, "out": b"", "err": b"Can't run subprocess" }

def set_loglevel(app,loglevel_string):
    logger.info("Setting Loglevel to %s" % loglevel_string)
    loglevels = {
        "WARN": logging.WARN,
        "INFO": logging.INFO,
        "DEBUG" : logging.DEBUG
    }
    app.logger.setLevel(loglevels[loglevel_string])
    logger.setLevel(loglevels[loglevel_string])

def get_loglevel(app):
    
    loglevels = {
        logging.WARN : "WARN",
        logging.INFO : "INFO",
        logging.DEBUG : "DEBUG"
    }
    return loglevels[app.logger.getEffectiveLevel()]

def hwi_get_config(specter):
    config = {
        'whitelisted_domains': 'http://127.0.0.1:25441/'
    }

    # if config.json file exists - load from it
    if os.path.isfile(os.path.join(specter.data_folder, "hwi_bridge_config.json")):
        with open(os.path.join(specter.data_folder, "hwi_bridge_config.json"), "r") as f:
            file_config = json.loads(f.read())
            deep_update(config, file_config)
    # otherwise - create one and assign unique id
    else:
        save_hwi_bridge_config(specter, config)
    return config

def save_hwi_bridge_config(specter, config):
    if 'whitelisted_domains' in config:
        whitelisted_domains = ''
        for url in config['whitelisted_domains'].split():
            if not url.endswith("/") and url != '*':
                # make sure the url end with a "/"
                url += "/"
            whitelisted_domains += url.strip() + '\n'
        config['whitelisted_domains'] = whitelisted_domains
    with open(os.path.join(specter.data_folder, 'hwi_bridge_config.json'), "w") as f:
        f.write(json.dumps(config, indent=4))

def der_to_bytes(derivation):
    items = derivation.split("/")
    if len(items) == 0:
        return b''
    if items[0] == 'm':
        items = items[1:]
    if items[-1] == '':
        items = items[:-1]
    res = b''
    for item in items:
        index = 0
        if item[-1] == 'h' or item[-1] == "'":
            index += 0x80000000
            item = item[:-1]
        index += int(item)
        res += index.to_bytes(4,'big')
    return res

def get_devices_with_keys_by_type(app, cosigners, wallet_type):
    devices = []
    prefix = "tpub"
    if app.specter.chain == "main":
        prefix = "xpub"
    for cosigner in cosigners:
        device = copy.deepcopy(cosigner)
        allowed_types = ['', wallet_type]
        device.keys = [key for key in device.keys if key.xpub.startswith(prefix) and key.key_type in allowed_types]
        devices.append(device)
    return devices