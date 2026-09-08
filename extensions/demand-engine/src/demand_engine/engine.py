from __future__ import annotations

from math import ceil

import numpy as np

from demand_engine.analytical.distributions import (
    binomial_stats,
    empirical_stats,
    exponential_renewal_stats,
    exponential_single_failure_stats,
    negative_binomial_stats,
    poisson_stats,
)
from demand_engine.enums import ExecutionMode, FailureProcessMode, ReliabilityModelType
from demand_engine.models import (
    CalculationInput,
    CalculationResult,
    ComparisonResult,
    ItemResult,
    RunResult,
)
from demand_engine.simulation import ConvergenceTracker, RandomSource, effective_minimum_runs
from demand_engine.version import (
    ENGINE_VERSION,
    FORMULA_VERSION,
    INPUT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
)
from demand_engine.weibull import weibull_conditional_failure_probability, weibull_renewal_mean


class DemandCalculationEngine:
    def calculate(self, calculation_input: CalculationInput, progress_callback=None, cancel_check=None) -> CalculationResult:
        modes = self._modes(calculation_input)
        runs = tuple(self._run(calculation_input, mode, progress_callback, cancel_check) for mode in modes)
        comparison = self._compare(runs) if len(runs) == 2 else None
        return CalculationResult(
            calculation_code=calculation_input.calculation_code,
            engine_version=ENGINE_VERSION,
            formula_version=FORMULA_VERSION,
            input_schema_version=INPUT_SCHEMA_VERSION,
            result_schema_version=RESULT_SCHEMA_VERSION,
            runs=runs,
            comparison=comparison,
        )

    @staticmethod
    def _modes(input_data):
        if input_data.requested_mode is ExecutionMode.COMPARE:
            return (ExecutionMode.ANALYTICAL, ExecutionMode.MONTE_CARLO)
        if input_data.requested_mode is ExecutionMode.AUTO:
            complex_item = any(
                item.reliability.model_type is ReliabilityModelType.WEIBULL
                or item.age_groups
                or item.common_shocks
                for item in input_data.items
            )
            return (ExecutionMode.MONTE_CARLO if complex_item else ExecutionMode.ANALYTICAL,)
        return (input_data.requested_mode,)

    def _run(self, input_data, mode, progress_callback, cancel_check):
        if mode is ExecutionMode.ANALYTICAL:
            items = tuple(self._analytical_item(input_data, item) for item in input_data.items)
            return RunResult(mode=mode, items=items)
        return self._monte_carlo(input_data, progress_callback, cancel_check)

    def _aggregate_exposure(self, input_data):
        return sum(stage.effective_hours * stage.adjustment_factor for stage in input_data.stages)

    def _analytical_item(self, input_data, item):
        exposure = self._aggregate_exposure(input_data)
        shock_factor = 1.0
        for shock in item.common_shocks:
            shock_factor *= (1.0 - shock.probability) + shock.probability * shock.multiplier
        exposure *= shock_factor
        rel = item.reliability
        quantiles = input_data.simulation.quantiles
        process = item.failure_process_mode
        if process is FailureProcessMode.AUTO:
            process = FailureProcessMode.RENEWAL if item.is_repairable else FailureProcessMode.SINGLE_FAILURE
        if rel.model_type is ReliabilityModelType.EXPONENTIAL:
            if process is FailureProcessMode.RENEWAL:
                stats = exponential_renewal_stats(item.installed_positions, rel.resolved_failure_rate, exposure, 1, item.replacement_ratio, quantiles)
            else:
                stats = exponential_single_failure_stats(item.installed_positions, rel.resolved_failure_rate, exposure, 1, item.replacement_ratio, quantiles)
        elif rel.model_type is ReliabilityModelType.WEIBULL:
            if process is FailureProcessMode.RENEWAL:
                mean = item.installed_positions * weibull_renewal_mean(exposure, rel.weibull_shape, rel.weibull_scale, max(0.25, exposure / 500)) * item.replacement_ratio
                stats = poisson_stats(mean, quantiles)
                stats = type(stats)(stats.mean, stats.variance, stats.standard_deviation, stats.quantiles, "MOMENT_MATCHED", ("WEIBULL_RENEWAL_QUANTILES_APPROXIMATED",))
            else:
                if item.age_groups:
                    probability = 0.0
                    for group in item.age_groups:
                        if group.distribution_type.value == "FIXED":
                            age = float(group.fixed_hours or 0)
                        elif group.distribution_type.value == "UNIFORM":
                            age = (float(group.minimum_hours or 0) + float(group.maximum_hours or 0)) / 2
                        elif group.distribution_type.value == "NORMAL":
                            age = float(group.mean_hours or 0)
                        else:
                            age = (float(group.minimum_hours or 0) + float(group.maximum_hours or 0) + float(group.mode_hours or 0)) / 3
                        probability += group.proportion * weibull_conditional_failure_probability(age, exposure, rel.weibull_shape, rel.weibull_scale)
                    probability *= item.replacement_ratio
                else:
                    probability = weibull_conditional_failure_probability(item.initial_age_hours, exposure, rel.weibull_shape, rel.weibull_scale) * item.replacement_ratio
                stats = binomial_stats(round(item.installed_positions), probability, quantiles)
        elif rel.model_type is ReliabilityModelType.BINOMIAL:
            ratio = exposure / (rel.reference_duration_hours or exposure or 1)
            probability = 1 - (1 - rel.binomial_probability) ** ratio
            stats = binomial_stats(round(item.installed_positions * rel.binomial_trials), probability * item.replacement_ratio, quantiles)
        elif rel.model_type is ReliabilityModelType.NEGATIVE_BINOMIAL:
            base_mean = rel.negative_binomial_r * (1 - rel.negative_binomial_p) / rel.negative_binomial_p
            ratio = exposure / (rel.reference_duration_hours or exposure or 1)
            mean = base_mean * ratio * item.installed_positions * item.replacement_ratio
            r = rel.negative_binomial_r
            p = r / (r + mean) if mean > 0 else 1
            stats = negative_binomial_stats(r, p, quantiles)
        else:
            ratio = exposure / (rel.reference_duration_hours or exposure or 1)
            stats = empirical_stats(rel.empirical_mean * ratio * item.installed_positions * item.replacement_ratio, rel.empirical_variance * ratio * item.installed_positions, quantiles)
        return self._item_result(item, stats, process)

    def _item_result(self, item, stats, process, samples=None):
        q = stats.quantiles
        def value(prob):
            if prob in q:
                return q[prob]
            keys = np.array(list(q), dtype=float)
            values = np.array(list(q.values()), dtype=float)
            return float(np.interp(prob, keys, values))
        target = value(item.target_service_level)
        gross = stats.mean
        if item.is_repairable:
            repair = item.repair
            net = gross * max(repair.condemnation_rate, 1 - repair.success_rate)
            pipeline = min(gross, gross * repair.turnaround_hours / max(repair.turnaround_hours, 1.0))
        else:
            net = gross
            pipeline = 0.0
        recommended = float(ceil(target))
        usable = max(0.0, item.inventory.available_quantity + item.inventory.in_transit_quantity - item.inventory.safety_stock)
        gap = max(0.0, recommended - usable)
        coverage = usable / recommended if recommended > 0 else 1.0
        return ItemResult(
            spare_part_id=item.spare_part_id,
            spare_part_code=item.spare_part_code,
            spare_part_name=item.spare_part_name,
            expected_demand=stats.mean,
            variance=stats.variance,
            standard_deviation=stats.standard_deviation,
            p50=value(0.5), p80=value(0.8), p90=value(0.9), p95=value(0.95), p99=value(0.99),
            target_service_level=item.target_service_level,
            target_quantile_demand=target,
            gross_replacement_demand=gross,
            repair_pipeline_demand=pipeline,
            repair_pipeline_peak=pipeline,
            net_consumption_demand=net,
            recommended_spare_quantity=recommended,
            usable_inventory=usable,
            net_demand_gap=gap,
            inventory_coverage_rate=coverage,
            selected_model_type=item.reliability.model_type,
            failure_process_mode=process,
            warnings=stats.warnings,
        )

    def _monte_carlo(self, input_data, progress_callback, cancel_check):
        random = RandomSource(input_data.random_seed)
        minimum = effective_minimum_runs(input_data.simulation)
        tracker = ConvergenceTracker(minimum, input_data.simulation.max_runs, input_data.simulation.required_stable_batches, input_data.simulation.mean_relative_tolerance, input_data.simulation.quantile_absolute_tolerance)
        all_samples = []
        converged = False
        while tracker.completed_runs < input_data.simulation.max_runs:
            if cancel_check and cancel_check():
                from demand_engine.exceptions import CalculationCancelledError
                raise CalculationCancelledError("calculation cancelled")
            size = min(input_data.simulation.batch_size, input_data.simulation.max_runs - tracker.completed_runs)
            columns = []
            for item in input_data.items:
                analytical = self._analytical_item(input_data, item)
                mean = analytical.expected_demand
                model = item.reliability.model_type
                if model is ReliabilityModelType.BINOMIAL or (not item.is_repairable and item.failure_process_mode is not FailureProcessMode.RENEWAL):
                    n = max(0, round(item.installed_positions))
                    p = min(1.0, mean / n) if n else 0.0
                    sample = random.binomial(n, p, size=size)
                elif model is ReliabilityModelType.NEGATIVE_BINOMIAL:
                    r = item.reliability.negative_binomial_r
                    p = r / (r + mean) if mean > 0 else 1.0
                    sample = random.negative_binomial(r, p, size=size)
                else:
                    sample = random.poisson(mean, size=size)
                columns.append(sample)
            batch = np.column_stack(columns) if columns else np.zeros((size, 0))
            all_samples.append(batch)
            converged = tracker.update(batch, target_quantile=max(input_data.simulation.quantiles))
            if progress_callback:
                progress_callback(tracker.completed_runs, input_data.simulation.max_runs, {"stable_batches": tracker.stable_batches})
            if converged:
                break
        combined = np.concatenate(all_samples, axis=0)
        items = []
        for index, item in enumerate(input_data.items):
            values = combined[:, index]
            quantiles = {float(q): float(np.quantile(values, q, method="higher")) for q in input_data.simulation.quantiles}
            stats = type("Stats", (), {
                "mean": float(np.mean(values)),
                "variance": float(np.var(values)),
                "standard_deviation": float(np.std(values)),
                "quantiles": quantiles,
                "warnings": () if converged else ("MONTE_CARLO_NOT_CONVERGED",),
            })()
            process = item.failure_process_mode
            if process is FailureProcessMode.AUTO:
                process = FailureProcessMode.RENEWAL if item.is_repairable else FailureProcessMode.SINGLE_FAILURE
            items.append(self._item_result(item, stats, process, values))
        return RunResult(
            mode=ExecutionMode.MONTE_CARLO,
            items=tuple(items),
            actual_simulation_runs=len(combined),
            converged=converged,
            stop_reason="CONVERGED" if converged else "MAX_RUNS_REACHED",
            warnings=() if converged else ("MONTE_CARLO_NOT_CONVERGED",),
        )

    @staticmethod
    def _compare(runs):
        left, right = runs
        differences = []
        levels = []
        for a, b in zip(left.items, right.items, strict=True):
            denominator = max(abs(a.expected_demand), 1e-12)
            relative = abs(a.expected_demand - b.expected_demand) / denominator
            levels.append(relative)
            differences.append({
                "spare_part_id": a.spare_part_id,
                "spare_part_code": a.spare_part_code,
                "mean_absolute_difference": abs(a.expected_demand - b.expected_demand),
                "mean_relative_difference": relative,
                "recommended_quantity_difference": abs(a.recommended_spare_quantity - b.recommended_spare_quantity),
            })
        maximum = max(levels, default=0.0)
        consistency = "CONSISTENT" if maximum <= 0.05 else "MINOR_DEVIATION" if maximum <= 0.2 else "MAJOR_DEVIATION"
        return ComparisonResult(consistency, tuple(differences))
