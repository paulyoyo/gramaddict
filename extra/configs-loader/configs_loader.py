import logging
from enum import Enum, auto
from itertools import cycle
from subprocess import Popen
from time import sleep

import yaml


class Mode(Enum):
    REPEAT = auto()
    SINGLE = auto()


logger = logging.getLogger("configs-loader")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)-12s ==> %(message)s",
    datefmt="%m/%d %H:%M:%S",
)

mode = Mode.REPEAT
# Pause between two runs, so a config that crashes at once can't relaunch
# the bot in a tight loop.
PAUSE_SECONDS = 60

if __name__ == "__main__":
    bot_run = ["gramaddict", "run", "--config"]

    def process_config():
        cur_conf = bot_run + [configs.get(config, {}).get("path", "")]
        logger.info(f"Starting `{config}` - {configs[config].get('path')}")
        # An argument list, no shell: with shell=True only "gramaddict" ran,
        # and "run --config <path>" was lost.
        with Popen(cur_conf, text=True) as p:
            code = p.wait()
        if code != 0:
            logger.warning(f"`{config}` exited with code {code}.")

    with open("configs-list.yml", "r") as stream:
        try:
            configs = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logger.error(exc)
            exit(1)

    if mode == Mode.REPEAT:
        for config in cycle(configs):
            process_config()
            sleep(PAUSE_SECONDS)
    elif mode == Mode.SINGLE:
        for config in configs:
            process_config()
    logger.info("Finish!")
