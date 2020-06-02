#!/usr/bin/env python3

import re
import math
import time
import socket
import sys
import os
import shutil
import atexit
from distutils.spawn import find_executable
from ast import literal_eval
from psutil import virtual_memory
import argparse
import subprocess
from pathlib import Path
import cv2
import numpy as np
import statistics
from scipy import interpolate
from scenedetect.video_manager import VideoManager
from scenedetect.scene_manager import SceneManager
from scenedetect.detectors import ContentDetector
import threading
from threading import Timer
from threading import Thread
import concurrent
from concurrent import futures
import datetime

from PyQt5.QtWidgets import QLabel, QProgressBar


if sys.version_info < (3, 7):
    print('Python 3.7+ required')
    sys.exit()

if sys.platform == 'linux':
    def restore_term():
        os.system("stty sane")

    atexit.register(restore_term)


class Av1an:
    frameCounterArray = []

    def __init__(self, argdict):
        """Av1an - Python all-in-one toolkit for AV1, VP9, VP8 encodes."""
        self.FFMPEG = 'ffmpeg -y -hide_banner -loglevel error'
        self.d = argdict
        if not find_executable('ffmpeg'):
            print('No ffmpeg found')
            sys.exit()

        # Changing pixel format, bit format
        self.d['pix_format'] = f' -strict -1 -pix_fmt {self.d.get("pix_format")}'

        self.d['ffmpeg_pipe'] = f' {self.d.get("pix_format")} {self.d.get("ffmpeg_cmd")} -f yuv4mpegpipe - |'


    def log(self, info):
        """Default logging function, write to file."""
        with open(self.d.get('logging'), 'a') as log:
            log.write(time.strftime('%X') + ' ' + info)

    def lineByLineCmd(self, cmd):
        popen = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE, universal_newlines=True)
        for stderr_line in iter(popen.stderr.readline, ""):
            yield stderr_line
        popen.stderr.close()
        return_code = popen.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, cmd)

    def call_cmd(self, cmd, capture_output=False):
        """Calling system shell, if capture_output=True output string will be returned."""
        if capture_output:
            return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout

        with open(self.d.get('logging'), 'a') as log:
            subprocess.run(cmd, shell=True, stdout=log, stderr=log)


    def determine_resources(self):
        """Returns number of workers that machine can handle with selected encoder."""
        cpu = os.cpu_count()
        ram = round(virtual_memory().total / 2 ** 30)

        if self.d.get('encoder') == 'aom' or self.d.get('encoder') == 'rav1e' or self.d.get('encoder') == 'vpx':
            self.d['workers'] = round(min(cpu / 2, ram / 1.5))

        elif self.d.get('encoder') == 'svt_av1':
            self.d['workers'] = round(min(cpu, ram)) // 5

        # fix if workers round up to 0
        if self.d.get('workers') == 0:
            self.d['workers'] = 1

    def set_logging(self):
        """Setting logging file."""
        if self.d.get('logging'):
            self.d['logging'] = f"{self.d.get('logging')}.log"
        else:
            self.d['logging'] = self.d.get('temp') / 'log.log'

    def setup(self):
        """Creating temporally folders when needed."""
        # Make temporal directories, and remove them if already presented
        if self.d.get('temp').exists() and self.d.get('resume'):
            pass
        else:
            if self.d.get('temp').is_dir():
                shutil.rmtree(self.d.get('temp'))
            (self.d.get('temp') / 'split').mkdir(parents=True)
            (self.d.get('temp') / 'encode').mkdir()

        if self.d.get('logging') is os.devnull:
            self.d['logging'] = self.d.get('temp') / 'log.log'

    def extract_audio(self, input_vid: Path):
        """Extracting audio from source, transcoding if needed."""
        audio_file = self.d.get('temp') / 'audio.mkv'
        if audio_file.exists():
            self.log('Reusing Audio File\n')
            return

        # Capture output to check if audio is present

        check = fr'{self.FFMPEG} -ss 0 -i "{input_vid}" -t 0 -vn -c:a copy -f null -'
        is_audio_here = len(self.call_cmd(check, capture_output=True)) == 0

        if is_audio_here:
            self.log(f'Audio processing\n'
                     f'Params: {self.d.get("audio_params")}\n')
            cmd = f'{self.FFMPEG} -i "{input_vid}" -vn ' \
                  f'{self.d.get("audio_params")} {audio_file}'
            self.call_cmd(cmd)

    def reduce_scenes(self, scenes):
        """Windows terminal can't handle more than ~600 scenes in length."""
        if len(scenes) > 600:
            scenes = scenes[::2]
            self.reduce_scenes(scenes)
        return scenes

    def scene_detect(self, video: Path):
        """
        Running PySceneDetect detection on source video for segmenting.
        Optimal threshold settings 15-50
        """
        # Skip scene detection if the user choose to
        if self.d.get('scenes') == '0':
            self.log('Skipping scene detection\n')
            return ''

        try:
            video_manager = VideoManager([str(video)])
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=self.d.get('threshold')))
            base_timecode = video_manager.get_base_timecode()

            # If stats file exists, load it.
            scenes = self.d.get('scenes')
            if scenes:
                scenes = Path(scenes)
                if scenes.exists():
                    # Read stats from CSV file opened in read mode:
                    with scenes.open() as stats_file:
                        stats = stats_file.read()
                        self.log('Using Saved Scenes\n')
                        return stats

            # Work on whole video
            video_manager.set_duration()

            # Set downscale factor to improve processing speed.
            video_manager.set_downscale_factor()

            # Start video_manager.
            video_manager.start()

            # Perform scene detection on video_manager.
            self.log(f'Starting scene detection Threshold: {self.d.get("threshold")}\n')
            scene_manager.detect_scenes(frame_source=video_manager, show_progress=sys.stdin.isatty())

            # Obtain list of detected scenes.
            scene_list = scene_manager.get_scene_list(base_timecode)

            self.log(f'Found scenes: {len(scene_list)}\n')

            scenes = [str(scene[0].get_frames()) for scene in scene_list]

            if (self.d["min_split_dist"] > 0):
                print("Removing short scenes")
                imod = -1
                for i in range(len(scenes) - 1):
                    if (int(scenes[i - imod]) - int(scenes[i - 1 - imod]) < self.d["min_split_dist"]):
                        del scenes[i - imod]
                        imod += 1
                if (video_manager.get_duration()[0].get_frames() - int(scenes[len(scenes) - 1]) < self.d["min_split_dist"]):
                    del scenes[len(scenes) - 1]
                print(f"There are {len(scenes)} scenes after pruning from {len(scene_list)}")

            if (self.d.get('min_splits')):
                # Reduce scenes intelligently to match number of workers
                workers = self.d.get('workers')
                ideal_split_pts = [math.floor(x * video_manager.get_duration()[0].get_frames()/(workers)) for x in range(workers)]
                print("Reducing scenes to " + str(workers) + " splits")
                intscenes = [int(x) for x in scenes]
                scenes = list()
                for i in ideal_split_pts:
                    # This will find the closest split points to the ideal ones
                    # for perfectly segmenting the video into n pieces
                    scenes.append(min(intscenes, key=lambda x:abs(x-i)))
                scenes = list(set(scenes))
                scenes.sort()
                scenes = [str(x) for x in scenes]

            # Fix for windows character limit
            if sys.platform != 'linux':
                scenes = self.reduce_scenes(scenes)

            scenes = ','.join(scenes[1:])

            return scenes

        except Exception as e:
            self.log(f'Error in PySceneDetect: {e}\n')
            print(f'Error in PySceneDetect{e}\n')
            print("Not splitting video. Possibly corrupted.")
            return []

    def split(self, video, frames):
        """Spliting video by frame numbers, or just copying video."""
        if len(frames) == 0:
            self.log('Copying video for encode\n')
            cmd = f'{self.FFMPEG} -i "{video}" -map_metadata -1 -an -c copy ' \
                  f'-avoid_negative_ts 1 "{self.d.get("temp") / "split" / "0.mkv"}"'
        else:
            self.log('Splitting video\n')
            cmd = f'{self.FFMPEG} -i "{video}" -map_metadata -1 -an -f segment -segment_frames {frames} ' \
                  f'-c copy -avoid_negative_ts 1 "{self.d.get("temp") / "split" / "%04d.mkv"}"'

        self.call_cmd(cmd)

    def frame_probe(self, source: Path):
        """Get frame count."""
        cmd = f'ffmpeg -hide_banner  -i "{source.absolute()}" -an  -map 0:v:0 -c:v copy -f null - '
        frames = (self.call_cmd(cmd, capture_output=True)).decode("utf-8")
        frames = int(frames[frames.rfind('frame=') + 6:frames.rfind('fps=')])
        return frames

    def frame_check(self, source: Path, encoded: Path):
        """Checking is source and encoded video frame count match."""

        status_file = Path(self.d.get("temp") / 'done.txt')

        if self.d.get("no_check"):
            s1 = self.frame_probe(source)
            with status_file.open('a') as done:
                done.write(f'({s1}, "{source.name}"), ')
                return

        s1, s2 = [self.frame_probe(i) for i in (source, encoded)]

        if s1 == s2:
            with status_file.open('a') as done:
                done.write(f'({s1}, "{source.name}"), ')
        else:
            print(f'Frame Count Differ for Source {source.name}: {s2}/{s1}')

    def get_video_queue(self, source_path: Path):
        """Returns sorted list of all videos that need to be encoded. Big first."""
        queue = [x for x in source_path.iterdir() if x.suffix == '.mkv']

        if self.d.get('resume'):
            done_file = self.d.get('temp') / 'done.txt'
            if done_file.exists():
                with open(done_file, 'r') as f:
                    data = [line for line in f]
                    if len(data) > 1:
                        data = literal_eval(data[1])
                        queue = [x for x in queue if x.name not in [x[1] for x in data]]

        queue = sorted(queue, key=lambda x: -x.stat().st_size)

        if len(queue) == 0:
            print('Error: No files found in .temp/split, probably splitting not working')
            sys.exit()

        return queue

    def aom_vpx_encode(self, input_files):
        """AOM encoding command composition."""
        encoder = self.d.get('encoder')

        if encoder == 'vpx':
            enc = 'vpxenc'

        if encoder == 'aom':
            enc = 'aomenc'

        single_p = f'{enc} --passes=1 '
        two_p_1 = f'{enc} --passes=2 --pass=1'
        two_p_2 = f'{enc} --passes=2 --pass=2'

        if self.d.get('passes') == 1:
            pass_1_commands = []
            for index in range(len(input_files)):
                pass_1_commands.append((f'-i "{input_files[index][0]}" {self.d.get("ffmpeg_pipe")} ' +
                f'  {single_p} {self.d.get("video_params")} -o "{input_files[index][1].with_suffix(".ivf")}" - ', index,
                (input_files[index][0], input_files[index][1].with_suffix('.ivf'))))
            return pass_1_commands

        if self.d.get('passes') == 2:
            pass_2_commands = []
            for index in range(len(input_files)):
                pass_2_commands.append((f'-i "{input_files[index][0]}" {self.d.get("ffmpeg_pipe")}' +
                    f' {two_p_1} {self.d.get("video_params")} --fpf="{input_files[index][0].with_suffix(".log")}" -o {os.devnull} - ',
                    f'-i "{input_files[index][0]}" {self.d.get("ffmpeg_pipe")}' +
                    f' {two_p_2} {self.d.get("video_params")} ' +
                    f'--fpf="{input_files[index][0].with_suffix(".log")}" -o "{input_files[index][1].with_suffix(".ivf")}" - ', index,
                    (input_files[index][0], input_files[index][1].with_suffix('.ivf'))))
            return pass_2_commands

    def compose_encoding_queue(self, files):
        """Composing encoding queue with splited videos."""
        input_files = [(self.d.get('temp') / "split" / file.name,
                       self.d.get('temp') / "encode" / file.name,
                       file) for file in files]

        queue = self.aom_vpx_encode(input_files)

        self.log(f'Encoding Queue Composed\n'
                 f'Encoder: {self.d.get("encoder").upper()} Queue Size: {len(queue)} Passes: {self.d.get("passes")}\n'
                 f'Params: {self.d.get("video_params")}\n')

        # Catch Error
        if len(queue) == 0:
            print('Error in making command queue')
            sys.exit()

        return queue

    @staticmethod
    def get_brightness(video):
        """Getting average brightness value for single video."""
        brightness = []
        cap = cv2.VideoCapture(video)
        try:
            while True:
                # Capture frame-by-frame
                _, frame = cap.read()

                # Our operations on the frame come here
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Display the resulting frame
                mean = cv2.mean(gray)
                brightness.append(mean[0])
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        except cv2.error:
            pass

        # When everything done, release the capture
        cap.release()
        brig_geom = round(statistics.geometric_mean([x+1 for x in brightness]), 1)

        return brig_geom

    @staticmethod
    def man_cq(command: str, cq: int):
        """
        If cq == -1 returns current value of cq in command
        Else return command with new cq value
        """
        mt = '--cq-level='
        if cq == -1:
            mt = '--cq-level='
            cq = int(command[command.find(mt) + 11:command.find(mt) + 13])
            return cq
        else:
            cmd = command[:command.find(mt) + 11] + str(cq) + command[command.find(mt) + 13:]
            return cmd

    def boost(self, command: str, br_geom, new_cq=0):
        """Based on average brightness of video decrease(boost) Quantize value for encoding."""
        cq = self.man_cq(command, -1)
        if not new_cq:
            if br_geom < 128:
                new_cq = cq - round((128 - br_geom) / 128 * self.d.get('br'))

                # Cap on boosting
                if new_cq < self.d.get('bl'):
                    new_cq = self.d.get('bl')
            else:
                new_cq = cq
        cmd = self.man_cq(command, new_cq)

        return cmd, new_cq

    def encode(self, commands):
        """Single encoder command queue and logging output."""
        # Passing encoding params to ffmpeg for encoding.
        # Replace ffmpeg with aom because ffmpeg aom doesn't work with parameters properly.
        try:
            st_time = time.time()
            source, target = Path(commands[-1][0]), Path(commands[-1][1])
            self.log(str(source))
            self.log(str(target))
            frame_probe_source = self.frame_probe(source)

            if self.d.get('boost'):
                br = self.get_brightness(source.absolute().as_posix())

                com0, cq = self.boost(commands[0], br)

                if self.d.get('passes') == 2:
                    com1, _ = self.boost(commands[1], br, cq)
                    commands = (com0, com1) + commands[2:]
                else:
                    commands = com0 + commands[1:]

                boost = f'Avg brightness: {br}\nAdjusted CQ: {cq}\n'
            else:
                boost = ''

            self.log(f'Enc:  {source.name}, {frame_probe_source} fr\n{boost}\n')

            # Queue execution
            frameCounterIndex = int(threading.currentThread().getName().split("_")[-1]) - 1
            startingFramecnt = self.frameCounterArray[frameCounterIndex]

            for i in range(len(commands[:-2])):
                self.log(rf'{self.FFMPEG} {commands[i]}')
                cmd = rf'{self.FFMPEG} {commands[i]}'
                if (i < (len(commands[:-2]) - 1)):
                    self.call_cmd(cmd)
                else :
                    regexp = re.compile("frame\s+\d+/(\d+)")
                    for line in self.lineByLineCmd(cmd):
                        try:
                            framecnt = int(re.findall(regexp, str(line))[-1])
                            Av1an.frameCounterArray[frameCounterIndex] = framecnt + startingFramecnt
                        except:
                            pass

            self.frame_check(source, target)

            frame_probe = self.frame_probe(target)

            enc_time = round(time.time() - st_time, 2)

            self.log(f'Done: {source.name} Fr: {frame_probe}\n'
                     f'Fps: {round(frame_probe / enc_time, 4)} Time: {enc_time} sec.\n')
            return self.frame_probe(source)
        except Exception as e:
            _, _, exc_tb = sys.exc_info()
            print(f'Error in encoding loop {e}\nAt line {exc_tb.tb_lineno}')
            return 0

    def concatenate_video(self):
        """With FFMPEG concatenate encoded segments into final file."""
        with open(f'{self.d.get("temp") / "concat" }', 'w') as f:

            encode_files = sorted((self.d.get('temp') / 'encode').iterdir())
            f.writelines(f"file '{file.absolute()}'\n" for file in encode_files)

        # Add the audio file if one was extracted from the input
        audio_file = self.d.get('temp') / "audio.mkv"
        if audio_file.exists():
            audio = f'-i {audio_file} -c:a copy'
        else:
            audio = ''

        try:
            cmd = f'{self.FFMPEG} -f concat -safe 0 -i "{self.d.get("temp") / "concat"}" ' \
                  f'{audio} -c copy -y "{self.d.get("output_file")}"'
            concat = self.call_cmd(cmd, capture_output=True)
            if len(concat) > 0:
                raise Exception

            self.log('Concatenated\n')

            # Delete temp folders
            if not self.d.get('keep'):
                shutil.rmtree(self.d.get('temp'))

        except Exception as e:
            print(f'Concatenation failed, FFmpeg error')
            self.log(f'Concatenation failed, aborting, error: {e}\n')
            sys.exit()

    runningFrameCounter = False
    startingTime = datetime.datetime.now()

    def countFrames(self, qinterface, totalFrames):
        if (self.runningFrameCounter):
            threading.Timer(1.0, self.countFrames, [qinterface, totalFrames]).start()
        frameCount = 0
        curTime = datetime.datetime.now()
        if ((curTime - self.startingTime).total_seconds() <= 0):
            return
        for i in self.frameCounterArray:
            frameCount += i
        qinterface.updateStatusProgress.emit("FR: " + str(frameCount) + "/" + str(totalFrames) + " FPS: " + str( frameCount / ((curTime - self.startingTime).total_seconds()))[0:5],
                                             math.floor(100 * frameCount / totalFrames))

    def encoding_loop(self, commands, qinterface):
        """Creating process pool for encoders, creating progress bar."""
        # Reduce if more workers than clips
        self.d['workers'] = min(len(commands), self.d.get('workers'))

        enc_path = self.d.get('temp') / 'split'
        done_path = self.d.get('temp') / 'done.txt'

        if self.d.get('resume') and done_path.exists():

            self.log('Resuming...\n')
            with open(done_path, 'r') as f:
                lines = [line for line in f]
                if len(lines) > 1:
                    data = literal_eval(lines[-1])
                    total = int(lines[0])
                    done = len([x[1] for x in data])
                    initial = sum([int(x[0]) for x in data])
                else:
                    done = 0
                    initial = 0
                    total = self.frame_probe(self.d.get('input_file'))
            self.log(f'Resumed with {done} encoded clips done\n\n')

        else:
            initial = 0
            with open(Path(self.d.get('temp') / 'done.txt'), 'w') as f:
                total = self.frame_probe(self.d.get('input_file'))
                f.write(f'{total}\n')

        clips = len([x for x in enc_path.iterdir() if x.suffix == ".mkv"])
        print(f'\rQueue: {clips} Workers: {self.d.get("workers")} Passes: {self.d.get("passes")}\n'
              f'Params: {self.d.get("video_params")}')
        doneFrames = initial
        Av1an.frameCounterArray = [0] * self.d['workers']
        self.runningFrameCounter = True
        self.startingTime = datetime.datetime.now()
        t = threading.Timer(1.0, self.countFrames, [qinterface, total])
        t.start()

        # We can use a with statement to ensure threads are cleaned up promptly
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.d['workers']) as executor:
            # Start the load operations and mark each future with its URL
            future_cmd = {executor.submit(self.encode, cmd): cmd for cmd in commands}
            for future in concurrent.futures.as_completed(future_cmd):
                dat = future_cmd[future]
                try:
                    data = future.result()
                except Exception as exc:
                    print(f'Encoding error: {exc}')
                    sys.exit()

    def setup_routine(self):
        """
        All pre encoding routine.
        Scene detection, splitting, audio extraction
        """
        if self.d.get('resume') and (self.d.get('temp') / 'done.txt').exists():
            self.set_logging()

        else:
            self.setup()
            self.set_logging()

            # Splitting video and sorting big-first
            framenums = self.scene_detect(self.d.get('input_file'))
            self.split(self.d.get('input_file'), framenums)

            # Extracting audio
            self.extract_audio(self.d.get('input_file'))

    def video_encoding(self, qinterface):
        """Encoding video on local machine."""
        self.setup_routine()

        files = self.get_video_queue(self.d.get('temp') / 'split')

        # Make encode queue
        commands = self.compose_encoding_queue(files)

        # Determine resources if workers don't set
        if self.d.get('workers') != 0:
            self.d['workers'] = self.d.get('workers')
        else:
            self.determine_resources()

        self.encoding_loop(commands, qinterface)
        self.runningFrameCounter = False

        self.concatenate_video()

    def main_thread(self, qinterface):
        """Main."""
        # Start time
        tm = time.time()
        # Parse initial arguments
        self.video_encoding(qinterface)
