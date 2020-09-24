import sys
import time
import codecs
import cursor
from spinners import Spinners


def decode_utf_8_text(text):
    try:
        return codecs.decode(text, 'utf-8')
    except:
        return text


def encode_utf_8_text(text):
    try:
        return codecs.encode(text, 'utf-8')
    except:
        return text


def animate(frames, name, iterations=4):
    CLEAR_LINE = '\033[K'
    if sys.version_info.major == 2:
        get_coded_text = encode_utf_8_text
    else:
        get_coded_text = decode_utf_8_text
    for i in range(iterations):
        for frame in frames:
            frame = get_coded_text(frame)
            output = "\r {0} {1}".format(frame, name)
            sys.stdout.write(output)
            sys.stdout.write(CLEAR_LINE)
            sys.stdout.flush()
            time.sleep(0.05)


def run_spinner(text):
    # cursor.hide()
    spinner = Spinners.dots
    frames = spinner.value['frames']
    animate(frames, text)
    # cursor.show()
