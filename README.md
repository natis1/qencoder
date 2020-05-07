# Finally, a qt encoder

qencoder is the gui you never knew you needed. With the power of scene-based splitting, it's now faster and easier than ever to encode with free codecs. Make the perfect video encodes with qencoder!

### Simple and easy to use
![Simple view](/screenshots/simple.png)

You don't need to have a deep understanding of how video works to take advantage of qencoder. With extremely easy to use and powerful presets, qencoder is for everyone.


### Powerful for those who need it
![Advanced view](/screenshots/complex.png)

qencoder features many useful features which make it a powerful tool. With scene based splitting, qencoder is the first ever gui to take advantage of systems with hundreds of cores. By splitting at the right moments, qencoder ensures your videos do not have any overhead from unneeded keyframes.

It also is the first gui capable of boosting dark scenes. Allowing you to use lower q values to avoid nasty artifacts like banding when needed.

It allows you to configure the colorspace of both your input and output, to ensure that your hdr video stays hdr.

Finally, it supports minimal splitting, the ideal mode for 2 pass vbr encodes. This mode makes as few splits as possible, keeping them all as far apart as possible so that the bitrate stays as variable as possible.

### The optimal encodes

qencoder takes advantage of the most modern and advanced free formats. It defaults to av1, a video codec so efficient it can get dvd-level quality in under 700MB. It uses aomenc by default, which, with threading, is the fastest and most efficient av1 encoder.

### Free videos

qencoder supports free codecs that can be encoded into webm. This means your videos can be shared and played on any html5 compliant browser. It also means that you do not need to worry about licensing fees or patent violation using it.

### Using qencoder

##### Windows

Download the latest 7zip in the "releases" section.

##### Linux

Git clone this repository:

```git clone https://github.com/natis1/qencoder```

```cd qencoder```

Then install ffmpeg and an up-to-date version of the aom encoder (for instance aomenc-git, on arch)

Then install the python requirements:

```pip install -r requirements.txt```

Then run it with

```./qencoder.py```

##### Legal note

app.ico modified from Wikimedia Commons by Videoplasty.com, CC-BY-SA 4.0
