#!/usr/bin/env python3

""" Plugin class of the GPU Memory Usage. """

import os
import time
from threading import Lock

import click
import pandas as pd
from distributed.diagnostics.plugin import SchedulerPlugin
from distributed.scheduler import Scheduler

from dask_memusage_gpus import definitions as defs
from dask_memusage_gpus import gpu_handler as gpu


class MemoryUsageGPUsPlugin(SchedulerPlugin):
    """
    GPUs Memory Usage Scheduler Plugin class

    Parameters
    ----------
    scheduler : Scheduler
        Dask Scheduler object.
    path : string
        Path of the record file.
    filetype : string
        Type of the record file. It can be CSV, JSON or dataframe.
    interval : int
        Interval of the time to fetch the GPU used memory by the plugin
        daemon.
    mem_max : bool
        Collect maximum memory usage.
    """
    def __init__(self, scheduler: Scheduler, path: str, filetype: str,
                 interval: int, mem_max: bool):
        """ Constructor of the MemoryUsageGPUsPlugin class. """
        SchedulerPlugin.__init__(self)

        self._scheduler: Scheduler = scheduler
        self._path: str = path
        self._filetype: str = filetype
        self._interval: int = interval
        self._mem_max: bool = mem_max

        self._lock = Lock()
        self._plugin_start = time.perf_counter()

        self._setup_record()

        self._workers_thread = gpu.WorkersThread(self._scheduler.address,
                                                 self._interval,
                                                 self._mem_max)

        self._workers_thread.start()

    def _setup_record(self):
        """
        Setup the record structure.
        """
        self._record = pd.DataFrame(columns=["task_key",
                                             "time",
                                             "min_gpu_memory_mb",
                                             "max_gpu_memory_mb",
                                             "worker_id"])

    def _record(self, key, min_gpu_mem_usage, max_gpu_mem_usage, worker_id):
        """
        Record a new data into the target file.

        Parameters
        ----------
        key : string
            Name of the task executed by Dask.
        min_gpu_mem_usage : int
            Lowest value of the GPU memory usage.
        max_gpu_mem_usage : int
            Highest value of the GPU memory usage.
        worker_id : string
            Identification of the worker for that row.
        """
        with self._lock:
            row = {'task_key': key,
                   'time': time.perf_counter() - self._plugin_start,
                   'min_gpu_memory_mb': min_gpu_mem_usage,
                   'max_gpu_memory_mb': max_gpu_mem_usage,
                   'worker_id': worker_id}

            new_row = pd.DataFrame([row])
            self._record = pd.concat([self._record,
                                      new_row], axis=0, ignore_index=True)

            if self._filetype.upper() == "CSV":
                header: bool = (not os.path.exists(self._path))

                self._record.to_csv(self._path, mode='a', header=header)

    def transition(self, key, start, finish, *args, **kwargs):
        """
        Transition function when a task is being processed.

        Parameters
        ----------
        key: string
            Identifier of the task.
        start : string
            Start state of the transition. One of released, waiting,
            processing, memory, error.
        finish : string
            Final state of the transition.
        *args, **kwargs : Any
            More options passed when transitioning This may include
            worker ID, compute time, etc.
        """
        if start == 'processing' and finish in ("memory", "erred"):
            worker_id = kwargs["worker"]
            min_gpu_mem_usage, max_gpu_mem_usage = \
                self._workers_thread.fetch_task_used_memory(worker_id)
            self._record(key, min_gpu_mem_usage, max_gpu_mem_usage, worker_id)

    async def before_close(self):
        """
        Shutdown plugin structures before closing the scheduler.
        """
        self._workers_thread.stop()


def validate_file_type(filetype):
    """
    Validate the type of the input file.

    Parameters
    ----------
    filetype : string
        Type of the input file to be recorded.

    Raises
    ------
    FileTypeException
        If the type does not match with the supported types.
    """
    if filetype not in defs.FILE_TYPES:
        raise defs.FileTypeException(f"'{filetype}' is not a valid "
                                     "output file.")


@click.command()
@click.option("--memusage-gpus-path", default=defs.DEFAULT_DATA_FILE)
@click.option("--memusage-gpus-type", default=defs.CSV)
@click.option("--memusage-gpus-interval", default=1)
@click.option("--memusage-gpus-max", is_flag=True)
def dask_setup(scheduler: Scheduler,
               memusage_gpus_path: str,
               memusage_gpus_type: str,
               memusage_gpus_interval: int,
               memusage_gpus_max: bool):
    """
    Setup Dask Scheduler Plugin.

    Parameters
    ----------
    scheduler : Scheduler
        Dask Scheduler object.
    memusage_gpus_path : string
        Path of the record file.
    memusage_gpus_filetype : string
        Type of the record file. It can be CSV, JSON or dataframe.
    memusage_gpus_interval : int
        Interval of the time to fetch the GPU used memory by the plugin
        daemon.
    memusage_gpus_max : bool
        Run plugin collection maximum memory usage.
    """
    validate_file_type(memusage_gpus_type)

    plugin = MemoryUsageGPUsPlugin(scheduler,
                                   memusage_gpus_path,
                                   memusage_gpus_type,
                                   memusage_gpus_interval,
                                   memusage_gpus_max)
    scheduler.add_plugin(plugin)
