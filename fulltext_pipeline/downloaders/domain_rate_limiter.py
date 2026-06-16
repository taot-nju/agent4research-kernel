"""
按域名控制 PDF 下载并发数和请求间隔。

设计目标：

1. 不同网站之间可以并行下载；
2. 同一个网站限制最大并发数；
3. 同一个网站的请求启动时间保持最小间隔；
4. 使用线程安全实现，供后续 ThreadPoolExecutor 复用；
5. 未明确配置的网站采用保守的默认策略。

当前数值是第一版保守配置，后续可根据小批量运行结果调整。
"""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urlparse


@dataclass(frozen=True)
class DomainPolicy:
    """单个域名的访问策略。"""

    max_concurrency: int
    min_interval_seconds: float


# 第一版采用相对保守的设置。
#
# max_concurrency：
#   同一时刻最多允许多少个请求正在访问该域名。
#
# min_interval_seconds：
#   同一域名相邻两个请求的启动时间至少间隔多久。
DOMAIN_POLICIES: dict[str, DomainPolicy] = {
    "arxiv.org": DomainPolicy(
        max_concurrency=1,
        min_interval_seconds=3.0,
    ),
    "openreview.net": DomainPolicy(
        max_concurrency=2,
        min_interval_seconds=1.0,
    ),
    "aclanthology.org": DomainPolicy(
        max_concurrency=2,
        min_interval_seconds=1.0,
    ),
    "ojs.aaai.org": DomainPolicy(
        max_concurrency=2,
        min_interval_seconds=1.5,
    ),
    "proceedings.mlr.press": DomainPolicy(
        max_concurrency=3,
        min_interval_seconds=0.5,
    ),
}


DEFAULT_DOMAIN_POLICY = DomainPolicy(
    max_concurrency=1,
    min_interval_seconds=2.0,
)


class _DomainState:
    """某个域名在运行期间共享的线程状态。"""

    def __init__(self, policy: DomainPolicy) -> None:
        if policy.max_concurrency <= 0:
            raise ValueError("max_concurrency 必须大于 0")

        if policy.min_interval_seconds < 0:
            raise ValueError(
                "min_interval_seconds 不能小于 0"
            )

        self.policy = policy

        # 控制该域名同时进行中的请求数量。
        self.semaphore = threading.BoundedSemaphore(
            policy.max_concurrency
        )

        # 控制相邻请求的启动间隔。
        self.schedule_lock = threading.Lock()
        self.next_allowed_time = 0.0


class DomainRateLimiter:
    """
    按域名进行并发和请求间隔控制。

    一个并发下载进程应共享一个 DomainRateLimiter 实例。
    """

    def __init__(
        self,
        policies: dict[str, DomainPolicy] | None = None,
        default_policy: DomainPolicy = DEFAULT_DOMAIN_POLICY,
    ) -> None:
        configured_policies = policies or DOMAIN_POLICIES

        self._policies = {
            domain.lower(): policy
            for domain, policy in configured_policies.items()
        }

        self._default_policy = default_policy

        self._states: dict[str, _DomainState] = {}
        self._states_lock = threading.Lock()

    @staticmethod
    def get_hostname(url: str) -> str:
        """从 URL 中提取小写域名。"""

        normalized_url = url.strip()

        if not normalized_url:
            raise ValueError("URL 不能为空")

        hostname = urlparse(normalized_url).hostname

        if not hostname:
            raise ValueError(
                f"无法从 URL 中解析域名：{normalized_url}"
            )

        return hostname.lower()

    def get_policy(self, hostname: str) -> DomainPolicy:
        """
        获取域名对应的策略。

        同时支持子域名匹配。例如：

            export.arxiv.org

        可以匹配：

            arxiv.org
        """

        normalized_hostname = hostname.lower()

        for configured_domain, policy in self._policies.items():
            if (
                normalized_hostname == configured_domain
                or normalized_hostname.endswith(
                    f".{configured_domain}"
                )
            ):
                return policy

        return self._default_policy

    def _get_state(self, hostname: str) -> _DomainState:
        """线程安全地获取或创建域名状态。"""

        with self._states_lock:
            state = self._states.get(hostname)

            if state is None:
                state = _DomainState(
                    self.get_policy(hostname)
                )
                self._states[hostname] = state

            return state

    @contextmanager
    def limit(self, url: str) -> Iterator[None]:
        """
        在上下文中获得访问某个 URL 的许可。

        使用方式：

            with limiter.limit(url):
                response = requests.get(url)

        退出上下文后会自动释放该域名的并发名额。
        """

        hostname = self.get_hostname(url)
        state = self._get_state(hostname)

        state.semaphore.acquire()

        try:
            # schedule_lock 保证同一域名的请求启动时间按顺序安排。
            with state.schedule_lock:
                current_time = time.monotonic()

                wait_seconds = (
                    state.next_allowed_time - current_time
                )

                if wait_seconds > 0:
                    time.sleep(wait_seconds)

                request_start_time = time.monotonic()

                state.next_allowed_time = (
                    request_start_time
                    + state.policy.min_interval_seconds
                )

            yield

        finally:
            state.semaphore.release()