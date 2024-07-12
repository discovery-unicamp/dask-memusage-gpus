#!/usr/bin/env python3

""" Plugin class of the GPU Memory Usage. """

import csv

import click
from distributed.diagnostics.plugin import SchedulerPlugin
from distributed.scheduler import Scheduler

from dask_memusage_for_gpus import definitions as defs
from dask_memusage_for_gpus import gpu_handler as gpu


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
    """
    def __init__(self, scheduler: Scheduler, path: str, filetype: str, interval: int):
        """ Constructor of the MemoryUsageGPUsPlugin class. """
        SchedulerPlugin.__init__(self)

        self._scheduler = scheduler
        self._path = path
        self._filetype = filetype
        self._interval = interval

        self._setup_filetype()

        self._workers_thread = gpu.WorkersThread(self._scheduler.address,
                                                 self._interval)

        self._workers_thread.start()

    def __write_csv(self, row, mode="w"):
        """
        Write a row in CSV file.

        Parameters
        ----------
        row : list
            The row to be written/appended in CSV file.
        mode : string
            Mode of the opened file (a new file or append into an existing
            file).
        """
        if isinstance(row, list):
            with open(self._path, mode, buffering=1) as fd:
                csv_file = csv.writer(fd)
                csv_file.writerow(row)

    def _setup_filetype(self):
        """
        Setup a file type if necessary.

        Obs: CVS requires the name of the columns first.
        """
        if self._filetype.upper() == "CSV":
            self.__write_csv(["task_key",
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
        if self._filetype.upper() == "CSV":
            self.__write_csv([key, min_gpu_mem_usage,
                              max_gpu_mem_usage, worker_id], mode="a")

    def transition(self, key, start, finish, stimulus_id, *args, **kwargs):
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
        stimulus_id : string
            ID of stimulus causing the transition.
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
@click.option("--memusage-for-gpus-path", default=defs.DEFAULT_DATA_FILE)
@click.option("--memusage-for-gpus-type", default=defs.CSV)
@click.option("--memusage-for-gpus-interval", default=1)
def dask_setup(scheduler: Scheduler,
               memusage_for_gpus_path: str,
               memusage_for_gpus_type: str,
               memusage_for_gpus_interval: int):
    """
    Setup Dask Scheduler Plugin.

    Parameters
    ----------
    scheduler : Scheduler
        Dask Scheduler object.
    memusage_for_gpus_path : string
        Path of the record file.
    memusage_for_gpus_filetype : string
        Type of the record file. It can be CSV, JSON or dataframe.
    memusage_for_gpus_interval : int
        Interval of the time to fetch the GPU used memory by the plugin
        daemon.
    """
    validate_file_type(memusage_for_gpus_type)

    plugin = MemoryUsageGPUsPlugin(scheduler,
                                   memusage_for_gpus_path,
                                   memusage_for_gpus_type,
                                   memusage_for_gpus_interval)
    scheduler.add_plugin(plugin)
