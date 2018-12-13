# prevent asap other modules from defining the root logger using basicConfig
import logging
logging.basicConfig(handlers=[logging.NullHandler()])

import argparse
import os
import sys

import automl
from automl.utils import config_load, datetime_iso, str2bool
from automl import log


parser = argparse.ArgumentParser()
parser.add_argument('framework', type=str,
                    help="The framework to evaluate as defined by default in resources/frameworks.yaml.")
parser.add_argument('benchmark', type=str, nargs='?', default='test',
                    help="The benchmark type to run as defined by default in resources/benchmarks/{benchmark}.yaml "
                         "or the path to a benchmark description file. Defaults to `%(default)s`.")
parser.add_argument('-m', '--mode', choices=['local', 'docker', 'aws'], default='local',
                    help="The mode that specifies how/where the benchmark tasks will be running. Defaults to %(default)s.")
parser.add_argument('-t', '--task', metavar='task_id', default=None,
                    help="The specific task name (as defined in the benchmark file) to run. "
                         "If not provided, then all tasks from the benchmark will be run.")
parser.add_argument('-f', '--fold', metavar='fold_num', type=int, nargs='*',
                    help="If task is provided, the specific fold(s) to run. "
                         "If fold is not provided, then all folds from the task definition will be run.")
parser.add_argument('-i', '--indir', metavar='input_dir', default=None,
                    help="Folder where datasets are loaded by default. Defaults to `input_dir` as defined in resources/config.yaml")
parser.add_argument('-o', '--outdir', metavar='output_dir', default=None,
                    help="Folder where all the outputs should be written. Defaults to `output_dir` as defined in resources/config.yaml")
parser.add_argument('-p', '--parallel', metavar='jobs_count', type=int, default=1,
                    help="The number of jobs (i.e. tasks or folds) that can run in parallel. Defaults to %(default)s. "
                         "Currently supported only in docker and aws mode.")
parser.add_argument('-s', '--setup', choices=['auto', 'skip', 'force', 'only'], default='auto',
                    help="Framework/platform setup mode. Defaults to %(default)s. "
                         "•auto: setup is executed only if strictly necessary. •skip: setup is skipped. •force: setup if always executed. •only: only setup is executed (no benchmark).")
# todo: we can probably remove this command line argument: by default, we're using the user default region as defined in ~/aws/config
#  on top of this, user can now override the aws.region setting in his custom ~/.config/automlbenchmark/config.yaml settings.
parser.add_argument('-r', '--region', metavar='aws_region', default=None,
                    help="The region on which to run the benchmark when using AWS.")
# parser.add_argument('--keep-instance', type=str2bool, metavar='true|false', nargs='?', const=True, default=True,
#                     help='Set to true [default] if reusing the same container instance(s) for all tasks (docker and aws mode only). '
#                          'If disabled in aws mode, we will try to distribute computing over multiple ec2 instances.')
# group = parser.add_mutually_exclusive_group()
# group.add_argument('--keep-instance', dest='keep_instance', action='store_true',
#                    help='Set to true [default] if reusing the same container instance(s) for all tasks (docker and aws mode only). '
#                         'If disabled in aws mode, we will try to distribute computing over multiple ec2 instances.')
# group.add_argument('--no-keep-instance', dest='keep_instance', action='store_false')
# parser.set_defaults(keep_instance=True)
args = parser.parse_args()

script_name = os.path.splitext(os.path.basename(__file__))[0]
log_dir = os.path.join(args.outdir if args.outdir else '.', 'logs')
os.makedirs(log_dir, exist_ok=True)
now_str = datetime_iso(date_sep='', time_sep='')
# now_str = datetime_iso(time=False, no_sep=True)
automl.logger.setup(log_file=os.path.join(log_dir, '{script}_{now}.log'.format(script=script_name, now=now_str)),
                    root_file=os.path.join(log_dir, '{script}_{now}_full.log'.format(script=script_name, now=now_str)),
                    root_level='DEBUG', console_level='INFO')

log.info("Running `%s` on `%s` benchmarks in `%s` mode", args.framework, args.benchmark, args.mode)
log.debug("script args: %s", args)

config = config_load("resources/config.yaml")
config_input = None
config.run_mode = args.mode
config.script = os.path.basename(__file__)
if args.indir:
    config.input_dir = args.indir
    # allowing config override from input_dir: useful for custom benchmarks executed on aws for example.
    config_input = config_load(os.path.join(args.indir, "config.yaml"))
if args.outdir:
    config.output_dir = args.outdir
# allowing config override from user_dir: useful to define custom benchmarks and frameworks for example.
config_user = config_load(os.path.join(config.user_dir, "config.yaml"))
# merging all configuration files
automl.resources.from_configs(config, config_input, config_user)

try:
    if args.mode == "local":
        bench = automl.Benchmark(args.framework, args.benchmark, parallel_jobs=args.parallel)
    elif args.mode == "docker":
        bench = automl.DockerBenchmark(args.framework, args.benchmark, parallel_jobs=args.parallel)
    elif args.mode == "aws":
        bench = automl.AWSBenchmark(args.framework, args.benchmark, parallel_jobs=args.parallel, region=args.region)
    # elif args.mode == "aws-remote":
    #     bench = automl.AWSRemoteBenchmark(args.framework, args.benchmark, parallel_jobs=args.parallel, region=args.region)
    else:
        raise ValueError("mode must be one of 'aws', 'docker' or 'local'.")

    if args.setup == 'only':
        log.warning("Setting up %s environment only for %s, no benchmark will be run", args.mode, args.framework)

    bench.setup(automl.Benchmark.SetupMode[args.setup])
    if args.setup != 'only':
        if args.task is None:
            res = bench.run(save_scores=True)
        else:
            res = bench.run_one(args.task, args.fold, save_scores=True)
except ValueError as e:
    log.error('\nERROR:\n%s', e)
    sys.exit(1)
