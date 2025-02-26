# Copyright 2020-2022 The Kubeflow Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""KFP SDK compiler CLI tool."""
import json
import logging
import os
import sys
from typing import Any, Callable, List, Mapping, Optional

import click
from kfp import compiler
from kfp.components import pipeline_context


def _compile_pipeline_function(
    pipeline_funcs: List[Callable],
    function_name: Optional[str],
    pipeline_parameters: Optional[Mapping[str, Any]],
    package_path: str,
    type_check: bool,
) -> None:
    """Compiles a pipeline function.

    Args:
      pipeline_funcs: A list of pipeline_functions.
      function_name: The name of the pipeline function to compile if there were
        multiple.
      pipeline_parameters: The pipeline parameters as a dict of {name: value}.
      package_path: The output path of the compiled result.
      type_check: Whether to enable the type checking.
    """
    if len(pipeline_funcs) == 0:
        raise ValueError(
            'A function with @dsl.pipeline decorator is required in the py file.'
        )

    if len(pipeline_funcs) > 1 and not function_name:
        func_names = [x.__name__ for x in pipeline_funcs]
        raise ValueError(
            'There are multiple pipelines: %s. Please specify --function.' %
            func_names)

    if function_name:
        pipeline_func = next(
            (x for x in pipeline_funcs if x.__name__ == function_name), None)
        if not pipeline_func:
            raise ValueError('The function "%s" does not exist. '
                             'Did you forget @dsl.pipeline decoration?' %
                             function_name)
    else:
        pipeline_func = pipeline_funcs[0]

    compiler.Compiler().compile(
        pipeline_func=pipeline_func,
        pipeline_parameters=pipeline_parameters,
        package_path=package_path,
        type_check=type_check)


class PipelineCollectorContext():

    def __enter__(self):
        pipeline_funcs = []

        def add_pipeline(func: Callable) -> Callable:
            pipeline_funcs.append(func)
            return func

        self.old_handler = pipeline_context.pipeline_decorator_handler
        pipeline_context.pipeline_decorator_handler = add_pipeline

        return pipeline_funcs

    def __exit__(self, *args):
        pipeline_context.pipeline_decorator_handler = self.old_handler


@click.command()
@click.option(
    '--py', type=str, required=True, help='Local absolute path to a py file.')
@click.option(
    '--output',
    type=str,
    required=True,
    help='Local path to the output PipelineJob JSON file.')
@click.option(
    '--function',
    'function_name',
    type=str,
    default=None,
    help='The name of the function to compile if there are multiple.')
@click.option(
    '--pipeline-parameters',
    type=str,
    default=None,
    help='The pipeline parameters in JSON dict format.')
@click.option(
    '--disable-type-check',
    is_flag=True,
    default=False,
    help='Disable the type check. Default: type check is not disabled.')
def dsl_compile(
    py: str,
    output: str,
    function_name: Optional[str] = None,
    pipeline_parameters: str = None,
    disable_type_check: bool = True,
) -> None:
    """Compiles a pipeline written in a .py file."""
    sys.path.insert(0, os.path.dirname(py))
    try:
        filename = os.path.basename(py)
        with PipelineCollectorContext() as pipeline_funcs:
            __import__(os.path.splitext(filename)[0])
        try:
            parsed_parameters = json.loads(
                pipeline_parameters) if pipeline_parameters is not None else {}
        except json.JSONDecodeError as e:
            logging.error(
                f"Failed to parse --pipeline-parameters argument: {pipeline_parameters}"
            )
            raise e
        _compile_pipeline_function(
            pipeline_funcs=pipeline_funcs,
            function_name=function_name,
            pipeline_parameters=parsed_parameters,
            package_path=output,
            type_check=not disable_type_check,
        )
    finally:
        del sys.path[0]


def main():
    logging.basicConfig(format='%(message)s', level=logging.INFO)
    try:
        dsl_compile(obj={}, auto_envvar_prefix='KFP')
    except Exception as e:
        click.echo(str(e), err=True)
        sys.exit(1)
