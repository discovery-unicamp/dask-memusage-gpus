#!/usr/bin/env python3

import csv

import click
from distributed.diagnostics.plugin import SchedulerPlugin
from distributed.scheduler import Scheduler

from dask_memusage_for_gpus import definitions as defs
from dask_memusage_for_gpus import gpu_handler as gpu


class MemoryUsageGPUsPlugin(SchedulerPlugin):
    def __init__(self, scheduler: Scheduler, path: str, filetype: str, interval: int):
        SchedulerPlugin.__init__(self)

        self._scheduler = scheduler
        self._path = path
        self._filetype = filetype
        self._interval = interval

        self._setup_filetype()

        self._workers_thread = gpu.WorkersThread(self._scheduler.address,
                                                 self._interval)

        self._workers_thread.start()

    def _setup_filetype(self):
        if self._filetype.upper() == "CSV":
            with open(self._path, "w", buffering=1) as fd:
                self._csv = csv.writer(fd)
                self._csv.writerow(["task_key",
                                    "min_gpu_memory_mb",
                                    "max_gpu_memory_mb"])

    def _register(self, key, min_gpu_mem_usage, max_gpu_mem_usage):
        if self._filetype.upper() == "CSV":
            self._csv.writerow([key, min_gpu_mem_usage, max_gpu_mem_usage])

    def transition(self, key, start, finish, *args, **kwargs):
        if start == 'processing' and finish in ("memory", "erred"):
            memory_usage = self._workers_thread.fetch_task_used_memory(kwargs["worker"])
            max_gpu_mem_usage = max(memory_usage)
            min_gpu_mem_usage = min(memory_usage)
            self._register(key, min_gpu_mem_usage, max_gpu_mem_usage)

    def before_close(self):
        self._workers_thread.cancel()


def validate_file_type(filetype):
    if filetype not in defs.FILE_TYPES:
        raise defs.FileTypeException(f"'{filetype}' is not a valid "
                                     "output file.")


@click.command()
@click.option("--memusage-for-gpus-path", default=defs.DEFAULT_DATA_FILE)
@click.option("--memusage-for-gpus-type", default=defs.CSV)
@click.option("--memusage-for-gpus-interval", default=1)
def dask_setup(scheduler: Scheduler,
               memusage_for_gpus_path: str,
               memusage_for_gpus_type: str,
               memusage_for_gpus_interval: int):
    validate_file_type(memusage_for_gpus_type)

    plugin = MemoryUsageGPUsPlugin(scheduler,
                                   memusage_for_gpus_path, 
                                   memusage_for_gpus_type,
                                   memusage_for_gpus_interval)
    scheduler.add_plugin(plugin)
