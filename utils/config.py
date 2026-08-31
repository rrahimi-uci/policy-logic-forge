"""
Configuration Management Module

Loads and manages configuration from config.json with environment variable
overrides.

This is a trimmed fork of policy-to-knowledge/apps/pipeline/utils/config.py,
kept in sync only for what ``agent_01`` through ``agent_12`` actually use.
Removed relative to the source: rule-type color palettes, priority-filter
buttons, and directory getters that existed only to serve the HTML visualizer
and the cross-graph comparison pipeline, neither of which is part of this repo.
See README.md for why.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
import re
from dotenv import load_dotenv

from utils.agent_names import output_dir_name

# Load environment variables from the repo-root .env at module level.
_repo_root = Path(__file__).resolve().parents[1]
_root_env_path = _repo_root / '.env'
if _root_env_path.exists():
    load_dotenv(dotenv_path=_root_env_path)

REASONING_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh", "max"})
MODEL_PROVIDERS = frozenset({"openai", "anthropic"})


class Config:
    """Configuration manager that loads settings from config.json and environment variables."""

    _instance = None
    _config = None
    _provider = None
    _source_file_name = None  # Name of the source file being processed (without extension)
    _batch_name = None  # Name of the batch/subdirectory being processed
    _domain = None  # Active compliance domain

    def __new__(cls, *args, **kwargs):
        """Singleton pattern to ensure only one config instance."""
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_path: Optional[str] = None, provider: Optional[str] = None, source_file_name: Optional[str] = None, batch_name: Optional[str] = None, domain: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config.json file. Defaults to config.json in project root.
            provider: Explicitly set provider ('openai' or 'anthropic'). If None,
                reads KG_PROVIDER and then llm.provider.
            source_file_name: Name of the source file being processed (without extension).
                            When set, outputs are organized by this name.
            batch_name: Name of the batch/subdirectory being processed.
                       When set, outputs are organized under this batch name.
                       Takes precedence over source_file_name for output paths.
            domain: Active compliance domain. If None, reads from config.json
                   'domain.active' or KG_DOMAIN environment variable.
        """
        if self._config is not None:
            if provider is not None:
                self._provider = provider
            if source_file_name is not None:
                self._source_file_name = source_file_name
            if batch_name is not None:
                self._batch_name = batch_name
            if domain is not None:
                self._domain = domain
            return

        if provider is not None:
            self._provider = provider

        if batch_name is not None:
            self._batch_name = batch_name
        elif os.getenv('KG_BATCH_NAME'):
            self._batch_name = os.getenv('KG_BATCH_NAME')

        if source_file_name is not None:
            self._source_file_name = source_file_name
        elif os.getenv('KG_SOURCE_FILE_NAME'):
            self._source_file_name = os.getenv('KG_SOURCE_FILE_NAME')

        if domain is not None:
            self._domain = domain
        elif os.getenv('KG_DOMAIN'):
            self._domain = os.getenv('KG_DOMAIN')

        if config_path is None:
            env_path = os.getenv("C2C_CONFIG_PATH")
            if env_path:
                config_path = env_path
            else:
                current_dir = Path(__file__).parent
                config_path = current_dir.parent / "config.json"

        self.config_path = Path(config_path)
        self._load_config()

    def _load_config(self):
        """Load configuration from JSON file.

        Falls back to ``config.example.json`` when ``config.json`` is absent so a
        fresh clone or the test suite work without a manual copy step.
        """
        path = self.config_path
        if not path.exists():
            example = path.with_name("config.example.json")
            if example.exists():
                path = example
            else:
                raise FileNotFoundError(
                    f"Configuration file not found: {self.config_path} "
                    f"(and no {example.name} fallback). "
                    "Copy config.example.json to config.json to get started."
                )

        with open(path, 'r') as f:
            self._config = json.load(f)

        self._config = self._process_env_vars(self._config)

    def _process_env_vars(self, config: Any) -> Any:
        """Recursively replace ${VAR_NAME} with environment variable values."""
        if isinstance(config, dict):
            return {key: self._process_env_vars(value) for key, value in config.items()}
        elif isinstance(config, list):
            return [self._process_env_vars(item) for item in config]
        elif isinstance(config, str):
            pattern = r'\$\{([^}]+)\}'
            matches = re.findall(pattern, config)
            for var_name in matches:
                env_value = os.getenv(var_name, '')
                config = config.replace(f'${{{var_name}}}', env_value)
            return config
        else:
            return config

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g. 'openai.api_key')."""
        keys = key_path.split('.')
        value = self._config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def get_openai_api_key(self) -> str:
        """Get OpenAI API key from config or environment."""
        api_key = self.get('openai.api_key', '')
        if not api_key:
            api_key = os.getenv('OPENAI_API_KEY', '')
        if not api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or update config.json"
            )
        return api_key

    def get_anthropic_api_key(self) -> str:
        """Get the Anthropic API key from config or environment."""
        api_key = self.get('anthropic.api_key', '') or os.getenv('ANTHROPIC_API_KEY', '')
        if not api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or update config.json"
            )
        return api_key

    def get_api_key(self) -> str:
        """Return the credential for the selected model provider."""
        if self.get_model_provider() == 'anthropic':
            return self.get_anthropic_api_key()
        return self.get_openai_api_key()

    def get_reasoning_model(self) -> str:
        """Get the configured reasoning model name."""
        override = os.getenv('KG_MODEL')
        if override:
            return override
        provider = self.get_model_provider()
        default = 'claude-opus-5' if provider == 'anthropic' else 'gpt-5.6-luna'
        return self.get(f'{provider}.models.reasoning', default)

    def get_reasoning_effort(self) -> str:
        """Get reasoning effort level (none, low, medium, high, xhigh, max).

        ``KG_REASONING_EFFORT`` permits a one-off run to override without
        editing a local ``config.json``.
        """
        effort = os.getenv(
            'KG_REASONING_EFFORT',
            self.get(
                f'{self.get_model_provider()}.models.reasoning_effort',
                self.get('openai.models.reasoning_effort', 'high'),
            ),
        )
        if effort not in REASONING_EFFORTS:
            allowed = ", ".join(sorted(REASONING_EFFORTS))
            raise ValueError(f"Unsupported reasoning effort {effort!r}; expected one of: {allowed}")
        return effort

    def get_model_provider(self) -> str:
        """Return and validate the selected model provider."""
        provider = (
            self._provider
            or os.getenv('KG_PROVIDER')
            or self.get('llm.provider', 'openai')
        ).strip().lower()
        if provider not in MODEL_PROVIDERS:
            allowed = ", ".join(sorted(MODEL_PROVIDERS))
            raise ValueError(f"Unsupported model provider {provider!r}; expected one of: {allowed}")
        return provider

    def get_pipeline_base_path(self) -> Path:
        """Get base path for pipeline outputs based on batch/source file name.

        Priority order:
        1. batch_name (if set): pipeline-output/{batch_name}/
        2. source_file_name (if set): pipeline-output/{source_file_name}/
        3. Neither: pipeline-output/
        """
        base = Path('pipeline-output')
        if self._batch_name:
            base = base / self._batch_name
        elif self._source_file_name:
            base = base / self._source_file_name
        return base

    def set_source_file_name(self, name: str):
        self._source_file_name = name

    def get_source_file_name(self) -> Optional[str]:
        return self._source_file_name

    def set_batch_name(self, name: str):
        self._batch_name = name

    def get_batch_name(self) -> Optional[str]:
        return self._batch_name

    def get_optimizer_model(self) -> str:
        """Get optimizer model name (used for prompt-optimization meta-agent calls)."""
        override = os.getenv('KG_OPTIMIZER_MODEL') or os.getenv('KG_MODEL')
        if override:
            return override
        provider = self.get_model_provider()
        return self.get(f'{provider}.models.optimizer', self.get_reasoning_model())

    def get_source_dir(self) -> Path:
        """Get source directory path."""
        return Path(self.get('directories.source', 'compliance-files'))

    def get_organized_dir(self) -> Path:
        """``agent_01`` output directory."""
        base = self.get_pipeline_base_path()
        return base / output_dir_name("agent_01")

    def get_entity_relationship_dir(self) -> Path:
        """``agent_02`` output directory."""
        base = self.get_pipeline_base_path()
        return base / output_dir_name("agent_02")

    def get_rules_extracted_dir(self) -> Path:
        """``agent_03`` output directory."""
        base = self.get_pipeline_base_path()
        return base / output_dir_name("agent_03")

    def get_rules_with_entities_dir(self) -> Path:
        """``agent_05`` output directory."""
        base = self.get_pipeline_base_path()
        return base / output_dir_name("agent_05")

    def get_optimized_dir(self) -> Path:
        """``agent_06``–``agent_09`` shared optimized-graph directory."""
        base = self.get_pipeline_base_path()
        return base / output_dir_name("agent_06")

    def get_dag_dir(self) -> Path:
        """``agent_10`` output directory."""
        base = self.get_pipeline_base_path()
        return base / output_dir_name("agent_10")

    def get_executable_models_dir(self) -> Path:
        """``agent_11`` DMN/BPMN model output directory."""
        base = self.get_pipeline_base_path()
        return base / output_dir_name("agent_11")

    def get_business_report_dir(self) -> Path:
        """``agent_12`` self-contained HTML report output directory."""
        return self.get_pipeline_base_path() / output_dir_name("agent_12")

    def get_target_rules(self) -> int:
        """Get target number of rules to extract."""
        env_target = os.getenv('TARGET_RULES')
        if env_target:
            return int(env_target)
        return self.get('rules_extractor.target_rules', 300)

    def get_n_iterations(self) -> int:
        """Get number of iterations for entity extraction."""
        env_iterations = os.getenv('N_ITERATIONS')
        if env_iterations:
            return int(env_iterations)
        return self.get('entity_extractor.n_iterations', 3)

    def get_chunk_size_target(self) -> int:
        return self.get('document_organizer.chunk_size_target', 2000)

    def get_max_chunk_size(self) -> int:
        return self.get('document_organizer.max_chunk_size', 3000)

    def get_min_chunk_size(self) -> int:
        return self.get('document_organizer.min_chunk_size', 500)

    def get_rules_per_batch(self) -> int:
        """Get number of rules to extract per batch."""
        env_val = os.getenv('KG_RULES_PER_BATCH')
        if env_val:
            value = int(env_val)
            if value < 1:
                raise ValueError('KG_RULES_PER_BATCH must be at least 1')
            return value
        return self.get('rules_extractor.rules_per_batch_openai',
                        self.get('rules_extractor.rules_per_batch', 10))

    def get_max_retries(self) -> int:
        """Get maximum number of API retries, with a run-time override."""
        env_val = os.getenv('KG_LLM_MAX_RETRIES') or os.getenv('KG_OPENAI_MAX_RETRIES')
        if env_val:
            return int(env_val)
        provider = self.get_model_provider()
        return self.get(f'{provider}.rate_limiting.max_retries', 3)

    def get_timeout(self) -> int:
        """Get API timeout in seconds, with a run-time override."""
        env_val = os.getenv('KG_LLM_TIMEOUT') or os.getenv('KG_OPENAI_TIMEOUT')
        if env_val:
            return int(env_val)
        provider = self.get_model_provider()
        return self.get(f'{provider}.rate_limiting.timeout', 300)

    # -- LLM defaults --

    def get_default_temperature(self) -> float:
        return self.get('llm.default_temperature', 0.7)

    def get_default_max_tokens(self) -> int:
        return self.get('llm.default_max_tokens', 8192)

    def get_default_model(self) -> str:
        return os.getenv('KG_MODEL') or self.get_reasoning_model()

    # -- Domain --

    def get_domain(self) -> str:
        """Get the active compliance domain."""
        if self._domain is not None:
            return self._domain
        return self.get('domain.active', 'nda_confidentiality')

    def set_domain(self, domain: str):
        self._domain = domain

    def get_domain_prompts_dir(self) -> Path:
        """Path to the active domain's prompts directory, e.g. domain-prompts/nda_confidentiality."""
        base = self.get('domain.prompts_base_dir', 'domain-prompts')
        return Path(base) / self.get_domain()

    def get_max_workers(self) -> int:
        """Get maximum number of parallel workers for pipeline operations."""
        env_val = os.getenv('MAX_WORKERS')
        if env_val:
            return int(env_val)
        return self.get('pipeline.max_workers', 80)

    def get_document_workers(self) -> int:
        """Get safe concurrent document subprocesses for standard CLI runs."""
        return max(1, int(self.get('pipeline.document_workers', 32)))

    def get_performance_profile(self) -> dict:
        """Return the centralized throughput/resilience profile."""
        value = self.get('pipeline.performance', {})
        return dict(value) if isinstance(value, dict) else {}

    def get_supported_extensions(self) -> list:
        return self.get('pipeline.supported_extensions', ['.pdf', '.txt', '.md', '.docx'])

    # -- Document organizer --

    def get_chunk_overlap(self) -> int:
        return self.get('document_organizer.chunk_overlap', 200)

    def get_csv_rows_per_chunk(self) -> int:
        return self.get('document_organizer.csv_rows_per_chunk', 50)

    def get_max_content_for_analysis(self) -> int:
        return self.get('document_organizer.max_content_for_analysis', 12000)

    def get_simple_chunk_size(self) -> int:
        return self.get('document_organizer.simple_chunk_size', 3000)

    def get_docx_fallback_chunk_size(self) -> int:
        return self.get('document_organizer.docx_fallback_chunk_size', 2000)

    # -- Entity extractor --

    def get_entity_extractor_temperature(self) -> float:
        return self.get('entity_extractor.temperature', 0.7)

    def get_entity_extractor_max_tokens(self) -> int:
        env_val = os.getenv('KG_ENTITY_EXTRACTOR_MAX_TOKENS')
        if env_val:
            return int(env_val)
        return self.get('entity_extractor.max_tokens', 8192)

    # -- Rules extractor --

    def get_rules_batch_size(self) -> int:
        return self.get('rules_extractor.batch_size', 8)

    def get_rules_max_content_length(self) -> int:
        env_val = os.getenv('KG_RULES_MAX_CONTENT_LENGTH')
        if env_val:
            return int(env_val)
        return self.get('rules_extractor.max_content_length', 8000)

    def get_rules_target_words_per_batch(self) -> int:
        env_val = os.getenv('KG_RULES_TARGET_WORDS_PER_BATCH')
        if env_val:
            return int(env_val)
        return self.get('rules_extractor.target_words_per_batch', 4500)

    def get_rules_chunk_overlap_words(self) -> int:
        """Word overlap between re-split windows of an oversized organized chunk.

        Full-coverage mode (the default -- see `read_text_files_batch`) never
        truncates a chunk with content loss; instead a chunk longer than
        `get_rules_max_content_length()` is re-split into overlapping windows
        so a fact stated right at a hard cut is never split across two
        windows with no shared context.
        """
        env_val = os.getenv('KG_RULES_CHUNK_OVERLAP_WORDS')
        if env_val:
            return int(env_val)
        return self.get('rules_extractor.chunk_overlap_words', 150)

    def get_pilot_batch_limit(self) -> Optional[int]:
        """Cap on the number of word-balanced batches agent_03 processes.

        `None` (the default) means full coverage: every organized chunk is
        read without truncation and every resulting batch is processed. Set
        only for a deliberately cheap pilot/smoke run -- a capped run must
        never be reported as corpus coverage (see
        `agents/agent_03_rules_extractor.py::read_text_files_batch`, and
        `chunk_coverage.json`'s `pilot_mode` field).
        """
        env_val = os.getenv('PILOT_BATCH_LIMIT')
        if env_val:
            return int(env_val)
        configured = self.get('rules_extractor.pilot_batch_limit', None)
        return int(configured) if configured is not None else None

    def get_rules_temperature(self) -> float:
        return self.get('rules_extractor.temperature', 0.7)

    def get_rules_max_tokens(self) -> int:
        env_val = os.getenv('KG_RULES_MAX_TOKENS')
        if env_val:
            return int(env_val)
        return self.get('rules_extractor.max_tokens', 32768)

    def get_rules_low_confidence_threshold(self) -> int:
        return self.get('rules_extractor.low_confidence_threshold', 70)

    def get_rules_default_confidence_score(self) -> int:
        return self.get('rules_extractor.default_confidence_score', 75)

    def get_rules_confidence_weights(self) -> dict:
        return self.get('rules_extractor.confidence_weights', {
            'extraction_clarity': 0.30,
            'numeric_precision': 0.25,
            'context_completeness': 0.20,
            'source_authority': 0.15,
            'logical_consistency': 0.10
        })

    # -- Optimizer (agent_06) --

    def get_optimizer_model_name(self) -> str:
        return self.get_optimizer_model()

    def get_optimizer_dedup_temperature(self) -> float:
        return self.get('optimizer.dedup_temperature', 0.2)

    def get_optimizer_dedup_max_tokens(self) -> int:
        return self.get('optimizer.dedup_max_tokens', 8192)

    def get_optimizer_dependency_temperature(self) -> float:
        return self.get('optimizer.dependency_temperature', 0.7)

    def get_optimizer_dependency_max_tokens(self) -> int:
        return self.get('optimizer.dependency_max_tokens', 16384)

    def get_optimizer_batch_size(self) -> int:
        raw = os.getenv('KG_OPTIMIZER_BATCH_SIZE')
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                pass
        return self.get('optimizer.batch_size', 50)

    def get_optimizer_dedup_batch_size(self) -> int:
        raw = os.getenv('KG_OPTIMIZER_DEDUP_BATCH_SIZE')
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                pass
        return self.get('optimizer.dedup_batch_size', 25)

    def get_optimizer_max_cross_batch_pairs(self) -> int:
        raw = os.getenv('KG_OPTIMIZER_MAX_CROSS_BATCH_PAIRS')
        if raw:
            try:
                return max(0, int(raw))
            except ValueError:
                pass
        return self.get('optimizer.max_cross_batch_pairs', 20)

    def get_optimizer_description_truncation_length(self) -> int:
        return self.get('optimizer.description_truncation_length', 500)

    def get_optimizer_batched_temperature(self) -> float:
        return self.get('optimizer.batched_temperature', 0.2)

    def get_optimizer_batched_max_tokens(self) -> int:
        return self.get('optimizer.batched_max_tokens', 16384)

    def get_optimizer_cross_batch_temperature(self) -> float:
        return self.get('optimizer.cross_batch_temperature', 0.2)

    def get_optimizer_cross_batch_max_tokens(self) -> int:
        return self.get('optimizer.cross_batch_max_tokens', 8192)

    def __repr__(self) -> str:
        return f"Config(config_path={self.config_path})"


# Global config instance
_config = None


def get_config(provider: Optional[str] = None, source_file_name: Optional[str] = None, batch_name: Optional[str] = None, domain: Optional[str] = None) -> Config:
    """Get global configuration instance."""
    global _config

    if provider is None:
        provider = os.getenv('KG_PROVIDER')

    if batch_name is None:
        batch_name = os.getenv('KG_BATCH_NAME')

    if domain is None:
        domain = os.getenv('KG_DOMAIN')

    if _config is None:
        _config = Config(provider=provider, source_file_name=source_file_name, batch_name=batch_name, domain=domain)
    else:
        if provider is not None:
            _config._provider = provider
        if source_file_name is not None:
            _config._source_file_name = source_file_name
        if batch_name is not None:
            _config._batch_name = batch_name
        if domain is not None:
            _config._domain = domain
    return _config


def reload_config(config_path: Optional[str] = None, source_file_name: Optional[str] = None, batch_name: Optional[str] = None, domain: Optional[str] = None, provider: Optional[str] = None):
    """Reload configuration from file."""
    global _config
    current_provider = provider or os.getenv('KG_PROVIDER')
    if current_provider:
        os.environ['KG_PROVIDER'] = current_provider
    _config = None
    Config._instance = None
    Config._config = None
    Config._source_file_name = None
    Config._batch_name = None
    Config._domain = None
    _config = Config(
        config_path,
        provider=current_provider,
        source_file_name=source_file_name,
        batch_name=batch_name,
        domain=domain,
    )
    return _config
