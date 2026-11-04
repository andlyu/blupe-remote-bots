#!/usr/bin/env python3
"""Bound filter threads for the task's canonical saved-video encoders."""
import os
import sys


def encoder_command(arguments):
    # libx264 threads are already bounded by the canonical exporter. FFmpeg's
    # RGB conversion filters otherwise choose threads from the host CPU count.
    return ['/usr/bin/ffmpeg','-filter_threads','1','-filter_complex_threads','1',*arguments]


def main():
    command=encoder_command(sys.argv[1:])
    os.execv(command[0],command)

if __name__=='__main__':main()
