
from qencoder.ffmpeg import frame_probe
from scipy import interpolate
from pathlib import Path
import subprocess
import numpy as np
import sys
from math import isnan
import os
from math import isnan
from pathlib import Path
from subprocess import PIPE, STDOUT
import json
import traceback

def read_vmaf_json(file, percentile):
    """Reads vmaf file with vmaf scores in it and return N percentile score from it.
    :return: N percentile score
    :rtype: float
    """
    with open(file, 'r') as f:
        file = json.load(f)
        vmafs = [x['metrics']['vmaf'] for x in file['frames']]

    vmafs = [float(x) for x in vmafs if isinstance(x, float)]
    calc = [x for x in vmafs if isinstance(x, float) and not isnan(x)]
    perc = round(np.percentile(calc, percentile), 2)
    return perc


def call_vmaf(source: Path, encoded: Path, n_threads, model, res = "1920x1080"):

    if model:
        mod = f":model_path={model}"
    else:
        mod = ''

    if n_threads:
        n_threads = f':n_threads={n_threads}'
    else:
        n_threads = ''

    # For vmaf calculation both source and encoded segment scaled to 1080
    # for proper vmaf calculation
    # Also it's required to use -r before both files of vmaf calculation to avoid errors
    fl = source.with_name(encoded.stem).with_suffix('.json').as_posix()
    cmd = ["ffmpeg", "-loglevel", "error", "-hide_banner", "-i", encoded.as_posix(), "-i", source.as_posix(), "-filter_complex", f'[0:v]scale={res}:flags=spline:force_original_aspect_ratio=decrease[distorted];[1:v]scale={res}:flags=spline:force_original_aspect_ratio=decrease[ref];[distorted][ref]libvmaf=log_fmt=json:log_path={fl}{mod}{n_threads}', "-f", "null", "-"]

    try:
        c = subprocess.run(cmd, stdout=PIPE, stderr=STDOUT)
        call = c.stdout
        # print(c.stdout.decode())
        if 'error' in call.decode().lower():
            print('\n\nERROR IN VMAF CALCULATION\n\n',call.decode())
            sys.exit(1)
    except Exception as e:
        print("Unable to run target vmaf cmd. This might be because lack of support in your ffmpeg")
        sys.exit(1)

    return fl


def x264_probes(video: Path, ffmpeg: str, probe_framerate):
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', "-i", video.as_posix()]
    if probe_framerate != 0:
        cmd = cmd + ["-r", str(probe_framerate)]
    cmd = cmd + ["-an"] + ffmpeg.split() + ["-c:v", "libx264", "-crf", "0", video.with_suffix(".mp4").as_posix()]
    subprocess.run(cmd)

def gen_probes_names(probe, q):
    """Make name of vmaf probe
    """
    return probe.with_name(f'v_{q}{probe.stem}').with_suffix('.ivf')


def probe_cmd(probe, q, ffmpeg_pipe, encoder, threads):
    """Generate and return commands for probes at set Q values
    """
    pipe = f'ffmpeg -y -hide_banner -loglevel error -i {probe} {ffmpeg_pipe}'
    cmd1 = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", probe.as_posix()] + ffmpeg_pipe.split()

    if encoder == 'aom':
        cmd = cmd1 + ["aomenc", "-q", "--passes=1", "--threads=" + str(threads), "--end-usage=q", "--cpu-used=6", "--cq-level=" + str(q), "-o", probe.with_name(f"v_{q}{probe.stem}").with_suffix(".ivf").as_posix(), "-"]
    else:
        cmd = cmd1 + ["vpxenc", "--codec=vp9", "--passes=1", "--pass=1", "--threads=" + str(threads), "--end-usage=q", "--cpu-used=9", "--cq-level=" + str(q), "-o", probe.with_name(f"v_{q}{probe.stem}").with_suffix(".ivf").as_posix(), "-"]
    return cmd


def get_target_q(scores, vmaf_target):
    x = [x[1] for x in sorted(scores)]
    y = [float(x[0]) for x in sorted(scores)]
    f = interpolate.interp1d(x, y, kind='cubic')
    xnew = np.linspace(min(x), max(x), max(x) - min(x))
    tl = list(zip(xnew, f(xnew)))
    q = min(tl, key=lambda x: abs(x[1] - vmaf_target))

    return int(q[0]), round(q[1],3)


def interpolate_data(vmaf_cq: list, vmaf_target):
    x = [x[1] for x in sorted(vmaf_cq)]
    y = [float(x[0]) for x in sorted(vmaf_cq)]

    # Interpolate data
    f = interpolate.interp1d(x, y, kind='cubic')
    xnew = np.linspace(min(x), max(x), max(x) - min(x))

    # Getting value closest to target
    tl = list(zip(xnew, f(xnew)))
    vmaf_target_cq = min(tl, key=lambda x: abs(x[1] - vmaf_target))
    return vmaf_target_cq, tl, f, xnew


def two_step_cmd(cmd: list):
    cm1 = []
    cm2 = []
    for i in range(len(cmd)):
        if (cmd[i] == "|"):
            cm1 = cmd[:i]
            cm2 = cmd[(i + 1):]
    cm1_pipe = subprocess.Popen(cm1, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    pipe = subprocess.call(cm2, stdin=cm1_pipe.stdout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

def vmaf_probe(probe, q, args):

    cmd = probe_cmd(probe, q, args['ffmpeg_pipe'], args['encoder'], args['threads'])
    two_step_cmd(cmd)
    #make_pipes(cmd).wait()
    # TODO: Add graphics here

    file = call_vmaf(probe, gen_probes_names(probe, q), args['threads'], args['vmaf_path'])
    score = read_vmaf_json(file, 25)

    return score


def early_skips(probe, source, frames, args):

    cq = [args['max_cq'], args['min_cq']]
    scores = []
    for i in (0, 1):

        score = vmaf_probe(probe, cq[i], args)
        scores.append((score, cq[i]))
        # Early Skip on big CQ
        if i == 0 and round(score) > args['vmaf_target']:
            print(f"File: {source.stem}, Fr: {frames}\n" \
            f"Q: {sorted([x[1] for x in scores])}, Early Skip High CQ\n" \
            f"Vmaf: {sorted([x[0] for x in scores], reverse=True)}\n" \
            f"Target Q: {args['max_cq']} Vmaf: {score}\n\n")

            return True, args['max_cq']

        # Early Skip on small CQ
        if i == 1 and round(score) < args['vmaf_target']:
            print(f"File: {source.stem}, Fr: {frames}\n" \
                f"Q: {sorted([x[1] for x in scores])}, Early Skip Low CQ\n" \
                f"Vmaf: {sorted([x[0] for x in scores], reverse=True)}\n" \
                f"Target Q: {args['min_cq']} Vmaf: {score}\n\n")

            return True, args['min_cq']

    return False, scores


def get_closest(q_list, q, positive=True):
    """Returns closest value from the list, ascending or descending
    """
    if positive:
        q_list = [x for x in q_list if x > q]
    else:
        q_list = [x for x in q_list if x < q]

    return min(q_list, key=lambda x:abs(x-q))


def target_vmaf_search(probe, source, frames, args):

    vmaf_cq = []
    q_list = [args['min_cq'], args['max_cq']]
    score = 0
    last_q = args['min_cq']
    next_q = args['max_cq']
    for _ in range(args['vmaf_steps'] - 2 ):

        new_point= (last_q + next_q) // 2
        last_q = new_point

        q_list.append(new_point)
        score = vmaf_probe(probe, new_point, args)
        next_q = get_closest(q_list, last_q, positive=score >= args['vmaf_target'])
        vmaf_cq.append((score, new_point))

    return vmaf_cq


def target_vmaf(source: Path, args):

    frames = frame_probe(source)
    probe = source.with_suffix(".mp4")
    vmaf_cq = []

    try:
        x264_probes(source, args['ffmpeg_cmd'], 4)

        skips, scores = early_skips(probe, source, frames, args)
        if skips:
            return scores
        else:
            vmaf_cq.extend(scores)

        scores = target_vmaf_search(probe, source, frames, args)

        vmaf_cq.extend(scores)

        q, q_vmaf = get_target_q(vmaf_cq, args['vmaf_target'] )

        print(f'File: {source.stem}, Fr: {frames}\n' \
            f'Q: {sorted([x[1] for x in vmaf_cq])}\n' \
            f'Vmaf: {sorted([x[0] for x in vmaf_cq], reverse=True)}\n' \
            f'Target Q: {q} Vmaf: {q_vmaf}\n\n')

        return q

    except Exception as e:
        _, _, exc_tb = sys.exc_info()
        print(f'Error in vmaf_target {e} \nAt line {exc_tb.tb_lineno}')
        traceback.print_exc()
        raise Exception
