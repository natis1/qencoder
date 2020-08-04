#!/usr/bin/env python3

import re
import math
import time
from time import sleep
import json
import sys
import os
import shutil
import atexit
import subprocess
import cv2
import statistics
import threading
import concurrent
import datetime
import traceback
import qencoder.ffmpeg
import qencoder.targetvmaf
import qencoder.aomkf
from distutils.spawn import find_executable
from ast import literal_eval
from psutil import virtual_memory
from pathlib import Path
from scipy import interpolate
try:
    from scenedetect.video_manager import VideoManager
    from scenedetect.scene_manager import SceneManager
    from scenedetect.detectors import ContentDetector
except ImportError as e:
    print("Unable to find pyscenedetect, disabling")
import concurrent.futures
from math import isnan


if sys.version_info < (3, 7):
    print('Python 3.7+ required')
    sys.exit()

if sys.platform == 'linux':
    def restore_term():
        os.system("stty sane")

    atexit.register(restore_term)

class Av1an:
    frameCounterArray = []

    def __init__(self, argdict, window):
        """Av1an - Python all-in-one toolkit for AV1, VP9, VP8 encodes."""
        self.FFMPEG = 'ffmpeg -y -hide_banner -loglevel error'
        self.d = argdict
        self.window = window
        if not find_executable('ffmpeg'):
            self.log('No ffmpeg found')
            sys.exit()

        # Changing pixel format, bit format
        self.d['pix_format'] = f' -strict -1 -pix_fmt {self.d.get("pix_format")}'

        self.d['ffmpeg_pipe'] = f' {self.d.get("pix_format")} {self.d.get("ffmpeg_cmd")} -f yuv4mpegpipe - |'


    def log(self, info):
        """Default logging function, write to file."""
        print(info)
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
            a = subprocess.run(cmd, shell=True, stdout=log, stderr=log)

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

    def reduce_scenes(self, scenes):
        """Windows terminal can't handle more than ~600 scenes in length."""
        if len(scenes) > 600:
            scenes = scenes[::2]
            self.reduce_scenes(scenes)
        return scenes


    def scene_detect(self, video: Path, qinterface, videostr):
        """
        Running PySceneDetect detection on source video for segmenting.
        Optimal threshold settings 15-50
        """
        # Skip scene detection if the user choose to
        if self.d.get('scenes') == '0':
            self.log('Skipping scene detection\n')
            return ''

        try:
            totalFrames = qencoder.ffmpeg.frame_probe(videostr)
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

            scenes = []
            kfScenes = qencoder.ffmpeg.get_keyframes(self.d.get('input_file'))

            if (self.d['better_split']):
                scenes = [0]
                stat_file = self.d['temp'] / 'keyframes.log'
                stat_file_str = self.d['temp_str'] + "/" + 'keyframes.log'
                scene_list = qencoder.aomkf.aom_keyframes(self.d['input_file'], self.d['input_file_str'], stat_file, stat_file_str, self.d['min_split_dist'], self.d['ffmpeg_pipe'], self.d['encoder'], self.d['threads'] * self.d['workers'], self.d['video_params'], qinterface)
                self.log(f'Found scenes: {len(scene_list)}. Original video has {len(kfScenes)} keyframes\n')
                if (not self.d.get("unsafe_split")):
                    for scene in scene_list:
                        if (scene in kfScenes):
                            scenes.append(str(scene))
                else:
                    for scene in scene_list:
                        scenes.append(str(scene))
            else:
                video_manager = VideoManager([str(video.as_posix())])
                scene_manager = SceneManager()
                scene_manager.add_detector(ContentDetector(threshold=self.d.get('threshold')))
                base_timecode = video_manager.get_base_timecode()

                # Work on whole video
                video_manager.set_duration()
                # Set downscale factor to improve processing speed.
                video_manager.set_downscale_factor()
                # Start video_manager.
                video_manager.start()
                # Perform scene detection on video_manager.
                self.log(f'Starting scene detection Threshold: {self.d.get("threshold")}\n')
                scene_manager.detect_scenes(frame_source=video_manager, show_progress=qinterface.istty)
                # Obtain list of detected scenes.
                scene_list = scene_manager.get_scene_list(base_timecode)
                self.log(f'Found scenes: {len(scene_list)}. Original video has {len(kfScenes)} keyframes\n')
                if (not self.d.get("unsafe_split")):
                    for scene in scene_list:
                        if (scene[0].get_frames() in kfScenes):
                            scenes.append(str(scene[0].get_frames()))
                else:
                    for scene in scene_list:
                        scenes.append(str(scene[0].get_frames()))

            if (not self.d.get("unsafe_split")):
                self.log(f'reduced to : {len(scenes)} after removing all non-matching.\nUse a format without iframes like ffv1 to avoid this.\n')

            if (self.d["min_split_dist"] > 0):
                self.log("Removing short scenes")
                imod = -1
                for i in range(len(scenes) - 1):
                    if (int(scenes[i - imod]) - int(scenes[i - 1 - imod]) < self.d["min_split_dist"]):
                        del scenes[i - imod]
                        imod += 1
                if (totalFrames - int(scenes[len(scenes) - 1]) < self.d["min_split_dist"]):
                    del scenes[len(scenes) - 1]
                self.log(f"There are {len(scenes)} scenes after pruning from {len(scene_list)}")

            if (self.d.get('min_splits')):
                # Reduce scenes intelligently to match number of workers
                workers = self.d.get('workers')
                ideal_split_pts = [math.floor(x * totalFrames/(workers)) for x in range(workers)]
                self.log("Reducing scenes to " + str(workers) + " splits")
                intscenes = [int(x) for x in scenes]
                scenes = list()
                for i in ideal_split_pts:
                    # This will find the closest split points to the ideal ones
                    # for perfectly segmenting the video into n pieces
                    scenes.append(min(intscenes, key=lambda x: abs(x-i)))
                scenes = list(set(scenes))
                scenes.sort()
                scenes = [str(x) for x in scenes]

            # Fix for windows character limit
            if sys.platform != 'linux':
                scenes = self.reduce_scenes(scenes)
            if (len(scenes) <= 1):
                return ['0']
            scenes = ','.join(scenes[1:])

            return scenes

        except Exception as e:
            self.log(f'Error in PySceneDetect: {e}\n')
            self.log("Not able to split video. Possibly corrupted.")
            raise Exception

    def split(self, video, frames):
        """Spliting video by frame numbers, or just copying video."""
        if len(frames) == 1:
            self.log('Copying video for encode\n')
            cmd = f'{self.FFMPEG} -i \'{video}\' -map_metadata -1 -an -c copy ' \
                  f'-avoid_negative_ts 1 \'{self.d.get("temp_str") + "/split/0.mkv"}\''
        else:
            self.log('Splitting video\n')
            cmd = f'{self.FFMPEG} -i \'{video}\' -map_metadata -1 -an -f segment -segment_frames {frames} ' \
                  f'-c copy -avoid_negative_ts 1 \'{self.d.get("temp_str") + "/split" + "/%04d.mkv"}\''
        self.log(cmd)
        a = self.call_cmd(cmd)

    def get_video_queue(self, temp: Path, resume):
        """
        Compose and returns sorted list of all files that need to be encoded. Big first.
        :param temp: Path to temp folder
        :param resume: Flag on should already encoded chunks be discarded from queue
        :return: Sorted big first list of chunks to encode
        """
        source_path = temp / 'split'
        queue = [x for x in source_path.iterdir() if x.suffix == '.mkv']

        done_file = temp / 'done.json'
        if resume and done_file.exists():
            try:
                with open(done_file) as f:
                    data = json.load(f)
                data = data['done'].keys()
                queue = [x for x in queue if x.name not in data]
            except Exception as e:
                _, _, exc_tb = sys.exc_info()
                self.log(f'Error at resuming {e}\nAt line {exc_tb.tb_lineno}')

        queue = sorted(queue, key=lambda x: -x.stat().st_size)

        if len(queue) == 0:
            er = 'Error: No files found in .temp/split, probably splitting not working'
            self.log(er)
            raise Exception

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
                p1IF0 = str(input_files[index][0]).replace("'", "'\"'\"'")
                p1IF1 = str(input_files[index][1]).replace("'", "'\"'\"'")
                suffix = os.path.splitext(input_files[index][1])[1]
                pass_1_commands.append((f'-i \'{p1IF0}\' {self.d.get("ffmpeg_pipe")} ' +
                f'  {single_p} {self.d.get("video_params")} -o \'{p1IF1 + ".ivf"}\' - ', index,
                (input_files[index][0], input_files[index][1].with_suffix(str(suffix) + ".ivf"))))
            return pass_1_commands

        if self.d.get('passes') == 2:
            pass_2_commands = []
            for index in range(len(input_files)):
                p1IF0 = str(input_files[index][0]).replace("'", "'\"'\"'")
                p1IF1 = str(input_files[index][1]).replace("'", "'\"'\"'")
                suffix = os.path.splitext(input_files[index][1])[1]
                pass_2_commands.append((f'-i \'{p1IF0}\' {self.d.get("ffmpeg_pipe")}' +
                    f' {two_p_1} {self.d.get("video_params")} --fpf=\'{p1IF0 + ".log"}\' -o {os.devnull} - ',
                    f'-i \'{p1IF0}\' {self.d.get("ffmpeg_pipe")}' +
                    f' {two_p_2} {self.d.get("video_params")} ' +
                    f'--fpf=\'{p1IF0 + ".log"}\' -o \'{p1IF1 + ".ivf"}\' - ', index,
                    (input_files[index][0], input_files[index][1].with_suffix(str(suffix) + ".ivf"))))
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
            self.log('Error in making command queue')
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
        """Return command with new cq value"""
        mt = '--cq-level='
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
        st_time = time.time()
        source, target = Path(commands[-1][0]), Path(commands[-1][1])
        source_str = str(source).replace("'", "'\"'\"'")
        target_str = str(target).replace("'", "'\"'\"'")
        frame_probe_source = qencoder.ffmpeg.frame_probe(source_str)

        if (self.d['use_vmaf']):
            tg_cq = qencoder.targetvmaf.target_vmaf(source, self.d)

            cm1 = self.man_cq(commands[0], tg_cq)

            if self.d.get('passes') == 2:
                cm2 = self.man_cq(commands[1], tg_cq)
                commands = (cm1, cm2) + commands[2:]
            else:
                commands = cm1 + commands[1:]

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
            else:
                regexp = re.compile("frame\\s+\\d+/(\\d+)")
                for line in self.lineByLineCmd(cmd):
                    try:
                        framecnt = int(re.findall(regexp, str(line))[-1])
                        Av1an.frameCounterArray[frameCounterIndex] = framecnt + startingFramecnt
                    except:
                        pass

        qencoder.ffmpeg.frame_check(source, source_str, target, target_str, self.d['temp'], False)

        frame_probe = qencoder.ffmpeg.frame_probe(target_str)

        enc_time = round(time.time() - st_time, 2)

        self.log(f'Done: {source.name} Fr: {frame_probe}\n'
                 f'Fps: {round(frame_probe / enc_time, 4)} Time: {enc_time} sec.\n')
        return qencoder.ffmpeg.frame_probe(source_str)

    runningFrameCounter = False
    startingTime = datetime.datetime.now()

    def countFrames(self, qinterface, totalFrames):
        if (self.runningFrameCounter):
            threading.Timer(0.2, self.countFrames, [qinterface, totalFrames]).start()
        frameCount = 0
        curTime = datetime.datetime.now()
        if ((curTime - self.startingTime).total_seconds() <= 0):
            return
        for i in self.frameCounterArray:
            frameCount += i
        qinterface.q.put([0,"FR: " + str(frameCount) + "/" + str(totalFrames) + " FPS: " + str( frameCount / ((curTime - self.startingTime).total_seconds()))[0:5],
                                             math.floor(90 * frameCount / totalFrames) + 10])

    def encoding_loop(self, commands, qinterface):
        """Creating process pool for encoders, creating progress bar."""
        # Reduce if more workers than clips
        self.d['workers'] = min(len(commands), self.d.get('workers'))

        enc_path = self.d.get('temp') / 'split'
        done_path = self.d.get('temp') / 'done.json'
        total = 1

        if self.d.get('resume') and done_path.exists():

            self.log('Resuming...\n')
            with open(done_path) as f:
                data = json.load(f)
                total = data['total']
                done = len(data['done'])
                initial = sum(data['done'].values())

            self.log(f'Resumed with {done} encoded clips done\n\n')

        else:
            done = 0
            initial = 0
            total = qencoder.ffmpeg.frame_probe(self.d.get('input_file_str'))
            d = {'total': total, 'done': {}}
            with open(done_path, 'w') as f:
                json.dump(d, f)

        clips = len([x for x in enc_path.iterdir() if x.suffix == ".mkv"])
        self.log(f'\rQueue: {clips} Workers: {self.d.get("workers")} Passes: {self.d.get("passes")}\n'
              f'Params: {self.d.get("video_params")}')
        doneFrames = initial
        Av1an.frameCounterArray = [0] * self.d['workers']
        self.runningFrameCounter = True
        self.startingTime = datetime.datetime.now()
        t = threading.Timer(0.2, self.countFrames, [qinterface, total])
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
                    self.log(f'Encoding error: {exc}')
                    traceback.print_exc()
                    sys.exit()

    def setup_routine(self, qinterface):
        """
        All pre encoding routine.
        Scene detection, splitting, audio extraction
        """
        if self.d.get('resume') and (self.d.get('temp') / 'done.txt').exists():
            self.set_logging()
            return 0

        else:
            self.setup()
            self.set_logging()

            # Splitting video and sorting big-first
            framenums = self.scene_detect(self.d.get('input_file'), qinterface, self.d.get('input_file_str'))
            if (len(framenums) == 0):
                return 1
            self.split(self.d.get('input_file_str'), framenums)

            # Extracting audio
            qencoder.ffmpeg.extract_audio(self.d.get('input_file_str'), self.d.get('temp_str'), self.d.get('audio_params'))
            return 0

    def video_encoding(self, qinterface):
        """Encoding video on local machine."""
        # Determine resources if workers don't set
        if self.d.get('workers') != 0:
            self.d['workers'] = self.d.get('workers')
        else:
            self.determine_resources()

        code = self.setup_routine(qinterface)
        if (code != 0):
            raise RuntimeError("Unable to encode video because splitting failed without any possibility of recovery.")

        files = self.get_video_queue(self.d.get('temp'), self.d['resume'])

        # Make encode queue
        commands = self.compose_encoding_queue(files)
        self.encoding_loop(commands, qinterface)
        self.runningFrameCounter = False
        qencoder.ffmpeg.concatenate_video(self.d['temp_str'], self.d['temp'], self.d['output_file_str'])
        sleep(0.2)
        if (not self.d.get('keep')):
            shutil.rmtree(self.d.get('temp'))
        qinterface.runningPav1n = False

    def main_thread(self, qinterface):
        """Main."""
        # Start time
        tm = time.time()
        # Parse initial arguments
        try:
            self.video_encoding(qinterface)
        except Exception as e:
            self.q.put([2, 0])
            sys.exit(1)
