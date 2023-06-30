from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, List, Optional

from langchainplus_sdk import EvaluationResult, RunEvaluator
from langchainplus_sdk.schemas import Example, Run
from pydantic import root_validator

from langchain.callbacks.manager import (
    AsyncCallbackManagerForChainRun,
    CallbackManagerForChainRun,
)
from langchain.chains.base import Chain
from langchain.schema import RUN_KEY, BaseOutputParser


class RunEvaluatorInputMapper:
    """Map the inputs of a run to the inputs of an evaluation."""

    @property
    def output_keys(self) -> List[str]:
        """The keys of the output of the input mapper."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement output_keys"
        )

    @abstractmethod
    def map(self, run: Run, example: Optional[Example] = None) -> Dict[str, Any]:
        """Maps the Run and Optional[Example] to a dictionary"""


class RunEvaluatorOutputParser(BaseOutputParser[EvaluationResult]):
    """Parse the output of a run."""

    eval_chain_output_key: str = "text"

    def parse_chain_output(self, output: Dict[str, Any]) -> EvaluationResult:
        """Parse the output of a run."""
        text = output[self.eval_chain_output_key]
        return self.parse(text)


class RunEvaluatorChain(Chain, RunEvaluator):
    """Evaluate Run and optional examples."""

    input_mapper: RunEvaluatorInputMapper
    """Maps the Run and Optional example to a dictionary for the eval chain."""
    eval_chain: Chain
    """The evaluation chain."""
    output_parser: RunEvaluatorOutputParser
    """Parse the output of the eval chain into feedback."""

    @root_validator
    def validate_mapper_keys(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that the input mapper and eval chain have matching keys."""
        input_mapper: RunEvaluatorInputMapper = values["input_mapper"]
        eval_chain: Chain = values["eval_chain"]
        if set(input_mapper.output_keys) != set(eval_chain.input_keys):
            raise ValueError(
                f"Input mapper output_keys ({input_mapper.output_keys}) "
                f"must match eval_chain input_keys ({eval_chain.input_keys})"
            )

    @property
    def input_keys(self) -> List[str]:
        """The keys of the input of the evaluation chain."""
        return ["run", "example"]

    @property
    def output_keys(self) -> List[str]:
        """The keys of the output of the evaluation chain."""
        return ["feedback"]

    def _call(
        self,
        inputs: Dict[str, Any],
        run_manager: Optional[CallbackManagerForChainRun] = None,
    ) -> Dict[str, Any]:
        """Call the evaluation chain."""
        run: Run = inputs["run"]
        example: Optional[Example] = inputs.get("example")
        chain_input = self.input_mapper.map(run, example)
        _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()
        callbacks = _run_manager.get_child()
        chain_output = self.eval_chain(
            chain_input, callbacks=callbacks, include_run_info=True
        )
        run_info = chain_output[RUN_KEY]
        feedback = self.output_parser.parse_chain_output(chain_output)
        feedback.evaluator_info[RUN_KEY] = run_info
        return {"feedback": feedback}

    async def _acall(
        self,
        inputs: Dict[str, Any],
        run_manager: AsyncCallbackManagerForChainRun | None = None,
    ) -> Dict[str, Any]:
        run: Run = inputs["run"]
        example: Optional[Example] = inputs.get("example")
        chain_input = self.input_mapper.map(run, example)
        _run_manager = run_manager or AsyncCallbackManagerForChainRun.get_noop_manager()
        callbacks = _run_manager.get_child()
        chain_output = await self.eval_chain.acall(
            chain_input,
            callbacks=callbacks,
            include_run_info=True,
        )
        run_info = chain_output[RUN_KEY]
        feedback = self.output_parser.parse_chain_output(chain_output)
        feedback.evaluator_info[RUN_KEY] = run_info
        return {"feedback": feedback}

    def evaluate_run(
        self, run: Run, example: Optional[Example] = None
    ) -> EvaluationResult:
        """Evaluate an example."""
        return self({"run": run, "example": example})["feedback"]

    async def aevaluate_run(
        self, run: Run, example: Optional[Example] = None
    ) -> EvaluationResult:
        """Evaluate an example."""
        result = await self.acall({"run": run, "example": example})
        return result["feedback"]
