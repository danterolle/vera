import json

from vera.training.arguments import assert_matching_recipe, recipe, training_arguments
from vera.training.data import encode_record, file_hash, read_records, verify_dataset
from vera.training.runtime import language_model_class, load_model, save_environment, save_json


def _check_inputs(args, configuration: dict) -> None:
    if args.smoke_report is not None:
        report = json.loads(args.smoke_report.read_text())
        if report.get("passed") is not True or report["recipe"]["mode"] != "smoke":
            raise ValueError("A successful smoke report is required")
        assert_matching_recipe(configuration, report["recipe"], smoke=True)
    if args.resume is not None:
        world = configuration["world_size"]
        required = [
            "trainer_state.json", "optimizer.pt", "scheduler.pt",
            "adapter_config.json", "adapter_model.safetensors", "recipe.json",
        ]
        required += (
            ["rng_state.pth"] if world == 1
            else [f"rng_state_{rank}.pth" for rank in range(world)]
        )
        if any(not (args.resume / name).is_file() for name in required):
            raise ValueError("--resume must point to a complete Trainer checkpoint")
        previous = json.loads((args.resume / "recipe.json").read_text())
        assert_matching_recipe(configuration, previous)
    elif args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError("Use a fresh output directory or explicitly pass --resume")


def check_dataset_suitability(mode: str, manifest: dict) -> None:
    if mode == "train" and (
        manifest.get("purpose") != "domain_sft"
        or manifest.get("origin") == "synthetic_template"
    ):
        raise ValueError(
            "Full training is blocked: the contract-bootstrap dataset is not a domain SFT dataset."
        )


def main() -> None:
    args = training_arguments()
    manifest = verify_dataset(args.data)
    check_dataset_suitability(args.mode, manifest)
    records = read_records(args.data, "train", 160 if args.mode == "smoke" else 0)
    validation = read_records(args.data, "validation", 40 if args.mode == "smoke" else 0)
    FastLanguageModel = language_model_class()
    import torch
    from accelerate import PartialState
    from datasets import Dataset
    from transformers import DataCollatorForSeq2Seq
    from trl import SFTConfig, SFTTrainer

    from vera.training.callbacks import TrainingGuard

    distributed = PartialState()
    configuration = recipe(args, file_hash(args.data / "manifest.json"))
    with distributed.main_process_first():
        if distributed.is_main_process:
            _check_inputs(args, configuration)
            args.output.mkdir(parents=True, exist_ok=True)
            save_json(args.output / "recipe.json", configuration)
            save_environment(args.output)
    model, tokenizer, hardware = load_model(args.max_length, args.rank)
    model.peft_config["default"].revision = configuration["revision"]
    FastLanguageModel.for_training(model)
    train_data = Dataset.from_list([
        encode_record(record, tokenizer, args.max_length) for record in records
    ])
    validation_data = Dataset.from_list([
        encode_record(record, tokenizer, args.max_length) for record in validation
    ])
    guard = TrainingGuard(configuration)
    trainer = SFTTrainer(
        model=model, processing_class=tokenizer,
        train_dataset=train_data, eval_dataset=validation_data,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer, padding=True, label_pad_token_id=-100,
        ),
        callbacks=[guard],
        args=SFTConfig(
            output_dir=str(args.output), per_device_train_batch_size=1,
            per_device_eval_batch_size=1, gradient_accumulation_steps=args.accumulation,
            learning_rate=args.learning_rate, num_train_epochs=args.epochs,
            max_steps=args.steps if args.mode == "smoke" else -1,
            warmup_ratio=0.05, weight_decay=0.01, max_grad_norm=1.0,
            optim="adamw_8bit", lr_scheduler_type="linear",
            fp16=False, bf16=hardware["native_bf16"] and not hardware["forced_float32"],
            logging_steps=1, logging_nan_inf_filter=False,
            eval_strategy="steps", eval_steps=50,
            save_strategy="steps", save_steps=10 if args.mode == "smoke" else 50,
            save_total_limit=2, save_only_model=False,
            dataloader_num_workers=0, dataset_num_proc=1,
            max_length=args.max_length, packing=False,
            dataset_kwargs={"skip_prepare_dataset": True},
            remove_unused_columns=False, ddp_find_unused_parameters=False,
            seed=3407, data_seed=3407, report_to="none",
        ),
    )
    outcome = trainer.train(resume_from_checkpoint=str(args.resume) if args.resume else None)
    guard.assert_updated()
    evaluation = trainer.evaluate()
    if distributed.is_main_process:
        adapter = args.output / "adapter"
        trainer.save_model(str(adapter))
        tokenizer.save_pretrained(str(adapter))
        save_json(adapter / "recipe.json", configuration)
        save_json(args.output / "report.json", {
            "passed": True, "recipe": configuration, "hardware": hardware,
            "optimizer_updates": guard.updates,
            "nonzero_gradient_updates": guard.nonzero_gradients,
            "adapter_changed": guard.before != guard.after,
            "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3,
            "training": outcome.metrics, "validation": evaluation,
            "quality_note": "Finite training is not evidence of improved answer quality.",
        })
    distributed.wait_for_everyone()


if __name__ == "__main__":
    main()
