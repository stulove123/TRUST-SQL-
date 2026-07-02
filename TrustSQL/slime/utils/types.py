from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union

import torch


@dataclass
class Sample:
    """The sample generated"""

    group_index: Optional[int] = None
    index: Optional[int] = None
    # prompt
    prompt: Union[str, list[dict[str, str]]] = ""
    tokens: list[int] = field(default_factory=list)
    # response
    response: str = ""
    response_length: int = 0
    label: Optional[str] = None
    # ✅ 修改：添加 list[float] 类型支持
    reward: Optional[Union[float, list[float], dict[str, Any]]] = None
    loss_mask: Optional[list[int]] = None
    weight_versions: list[str] = field(default_factory=list)
    rollout_log_probs: Optional[list[float]] = None
    rollout_routed_experts: Optional[list[list[int]]] = None

    class Status(Enum):
        PENDING = "pending"
        COMPLETED = "completed"
        TRUNCATED = "truncated"
        ABORTED = "aborted"

    status: Status = Status.PENDING

    metadata: dict = field(default_factory=dict)
    train_metadata: Optional[dict] = None

    class SpecInfo:
        spec_accept_token_num: int = 0
        spec_draft_token_num: int = 0
        spec_verify_ct: int = 0
        spec_accept_rate: float = 0.0
        spec_accept_length: float = 0.0

        def add(self, meta_info: dict, response_length: int):
            self.spec_accept_token_num += meta_info["spec_accept_token_num"]
            self.spec_draft_token_num += meta_info["spec_draft_token_num"]
            self.spec_verify_ct += meta_info["spec_verify_ct"]
            if self.spec_draft_token_num > 0:
                self.spec_accept_rate = self.spec_accept_token_num / self.spec_draft_token_num
            if self.spec_verify_ct > 0:
                self.spec_accept_length = response_length / self.spec_verify_ct

    spec_info: SpecInfo = field(default_factory=SpecInfo)

    def to_dict(self):
        value = self.__dict__.copy()
        value["status"] = self.status.value
        return value

    @staticmethod
    def from_dict(data: dict):
        data["status"] = Sample.Status(data["status"])
        return Sample(**data)

    def get_reward_value(self, args) -> Union[float, list[float]]:
        """
        获取 reward 值
        ✅ 修改：支持返回 list[float]（token-level reward）
        
        Returns:
            float: sentence-level reward
            list[float]: token-level reward
        """
        if not args.reward_key:
            return self.reward
        else:
            if isinstance(self.reward, dict):
                return self.reward[args.reward_key]
            else:
                return self.reward

    @property
    def effective_response_length(self):
        return sum(self.loss_mask) if self.loss_mask is not None else self.response_length


@dataclass
class ParamInfo:
    name: str
    dtype: torch.dtype
    shape: torch.Size
    attrs: dict
    size: int
    src_rank: int


RolloutBatch = dict[str, list[torch.Tensor] | list[int] | list[float] | list[str]]