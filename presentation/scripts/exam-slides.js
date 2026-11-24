(() => {
  const repo = "https://github.com/danterolle/vera/blob/main";
  const docs = `${repo}/docs`;

  const bar = (label, value, max) =>
    `<span class="bar-label">${label} <strong>${value}/${max}</strong></span>
     <meter min="0" max="${max}" value="${value}" aria-label="${label}: ${value} of ${max}"></meter>`;

  const cell = (label, value, max) =>
    `<td>${value}/${max}
     <meter min="0" max="${max}" value="${value}" aria-label="${label}: ${value} of ${max}"></meter></td>`;

  const pair = (metric, left, right, max, [baseline, variant] = ["Graph off", "Graph on"]) =>
    `<tr><th scope="row">${metric}</th>
     ${cell(`${metric}, ${baseline}`, left, max)}${cell(`${metric}, ${variant}`, right, max)}</tr>`;

  document.querySelector("#retrieval").insertAdjacentHTML("afterend", `
    <section id="graph-comparison">
      <h2>What changes when the graph is enabled?</h2>
      <p class="lede">We ran 12 definition queries twice, once with Kuzu off and once with it on. Both runs used the same bundled records and deterministic provider.</p>
      <table class="data-table grouped">
        <thead><tr><th scope="col">Metric</th><th scope="col">Graph off</th><th scope="col">Graph on</th></tr></thead>
        <tbody>
          ${pair("Expected record ranked first", 11, 12, 12)}
          ${pair("Expected record among the first five", 12, 12, 12)}
          ${pair("Expected record cited in a validated claim", 12, 12, 12)}
        </tbody>
      </table>
      <p class="callout">For “Define Remote Services”, Kuzu resolved <code>T1021</code> and moved its record ahead of <code>T1210</code>. Both runs still cited the expected record. With Kuzu on, every query cited its target through a graph record.</p>
      <p class="caption">The probe measures ranking and provenance with the deterministic provider. Evaluating generated answers requires a separate comparison. See “Paired retrieval probe” in the technical report.</p>
    </section>`);

  document.querySelector("#review").insertAdjacentHTML("afterend", `
    <section class="telemetry" id="review-trace">
      <h2>One replay, from detection to review</h2>
      <p class="lede">We ran the bundled SYN replay with the deterministic provider and Kuzu enabled, then rejected the held draft in the isolated database.</p>
      <ol class="flow">
        <li><b>01</b>20 simulated events</li><li><b>02</b>One <code>TCP-SYN-BURST</code> alert</li>
        <li><b>03</b><code>FULL</code> route</li><li><b>04</b>Pending review</li><li><b>05</b>Rejected</li>
      </ol>
      <div class="grid two">
        <article><h3>Why it paused</h3><p>The detector marked the signal high severity. The review gate blocked publication without treating the alert as evidence of compromise.</p></article>
        <article><h3>What the state showed</h3><p>Kuzu had zero run nodes before analysis, during review and after rejection. The report stayed out of published history. We recorded the order of the transitions without timing each step.</p></article>
      </div>
    </section>`);

  document.querySelector("#runtime").insertAdjacentHTML("afterend", `
    <section id="runtime-budgets">
      <h2>How VERA bounds work per analysis</h2>
      <div class="grid two indexed">
        <article><h3>Model calls: 4 by default</h3><p>The default budget covers interpretation, drafting and retries. If you enable ReAct with its default three steps, the automatic budget rises to six model calls.</p></article>
        <article><h3>Tool calls: 12 by default</h3><p>The budget limits external lookups. When it runs out, skipped sources remain visible as unavailable.</p></article>
        <article><h3>Corpus retrieval: 5 candidates</h3><p>The default local corpus search can return up to five candidates. Curated knowledge and optional graph retrieval contribute separate evidence.</p></article>
        <article><h3>Output budget: 1,024 tokens</h3><p>The default output limit applies per OpenAI-compatible model call. Human review allows up to two revisions.</p></article>
      </div>
      <p class="caption"><a href="${docs}/architecture.md#budgets-and-persistence">Runtime budgets</a> · <a href="${repo}/src/vera/config.py">Configuration defaults</a></p>
    </section>`);

  document.querySelector("#step-400").insertAdjacentHTML("beforebegin", `
    <section id="checkpoint-comparison">
      <h2>What did another 240 updates improve?</h2>
      <div class="chart-split">
        <figure class="latency">
          <figcaption>Validation summaries identical to the target</figcaption>
          <div class="dataset-bars">
            ${bar("Base", 0, 33)}${bar("Step 160", 29, 33)}${bar("Step 400", 33, 33)}
          </div>
        </figure>
        <article><h3>Checkpoint comparison</h3><p>We used the same 33 prompts and decoding settings at both checkpoints. Every answer used the expected schema. The later checkpoint reproduced more target summaries, which leaves open whether the analysis improved.</p></article>
      </div>
      <p class="caption">Step 400 was planned before the resumed run. The test split did not select the checkpoint. <a href="${docs}/finetuning-run-20261101.md#validation">Source: paired validation</a>.</p>
    </section>`);

  document.querySelector("#step-400-families").insertAdjacentHTML("afterend", `
    <section id="retrieval-audit">
      <h2>Finding the record did not prevent a refusal</h2>
      <div class="benchmark">
        <figure class="latency">
          <figcaption>Queries where the audit found the expected record</figcaption>
          <div class="dataset-bars">
            ${bar("Hybrid with hash embeddings", 22, 30)}
            ${bar("Lexical ranking", 23, 30)}
            ${bar("Hybrid with Sentence Transformers", 24, 30)}
          </div>
        </figure>
        <figure class="latency">
          <figcaption>In-domain questions marked out of scope</figcaption>
          <div class="dataset-bars">${bar("Base", 6, 30)}${bar("Step-400 adapter", 19, 30)}</div>
        </figure>
      </div>
      <p class="callout">Of the adapter’s 19 refusals, 16 concerned records that were already in the corpus and retrievable directly. Changing the embedding backend did not fix the refusals in the 10-case follow-up.</p>
      <p class="caption"><a href="${docs}/finetuning-adapter-assessment.md#scope-probe-refusal-in-both-directions-2026-11-09">Source: historical scope and retrieval audit</a>. The audit predates the current runtime and evaluated the step-400 adapter.</p>
    </section>`);

  document.querySelector("#retrieval-audit").insertAdjacentHTML("afterend", `
    <section id="step-400-test-pack">
      <h2>Step 400: contract checks across 220 test rows</h2>
      <table class="data-table grouped">
        <thead><tr><th scope="col">Metric</th><th scope="col">Base</th><th scope="col">Step-400 adapter</th></tr></thead>
        <tbody>
          ${pair("Valid JSON", 202, 220, 220, ["Base", "Step-400 adapter"])}
          ${pair("Valid answer schema", 192, 220, 220, ["Base", "Step-400 adapter"])}
          ${pair("Strict contract pass", 86, 219, 220, ["Base", "Step-400 adapter"])}
        </tbody>
      </table>
      <p class="callout">The adapter passed the strict checks on 219 rows and reproduced the target summary on 209. The selection shared 40 targets with training, and 38 rows duplicated another target.</p>
      <p class="caption"><a href="${docs}/finetuning-step400-heldout.md#test-split-pack-220-cases">Source: 220-case test-split pack</a>. This historical comparison uses synthetic targets.</p>
    </section>`);

  document.querySelector("#v4-training").insertAdjacentHTML("afterend", `
    <section id="v4-alert-coverage">
      <h2>V4 adds scenarios with multiple alerts</h2>
      <p class="lede">The step-400 training targets covered zero or one signal. V4 added controlled replays with two and three so the model could learn to report multiple observations.</p>
      <table class="data-table" aria-label="V4 examples grouped by detector signal count">
        <thead><tr><th scope="col">Split</th><th scope="col">0 signals</th><th scope="col">1 signal</th><th scope="col">2 signals</th><th scope="col">3 signals</th></tr></thead>
        <tbody>
          <tr><th scope="row">Training</th><td>5,316</td><td>40</td><td>30</td><td>20</td></tr>
          <tr><th scope="row">Validation</th><td>662</td><td>6</td><td>12</td><td>6</td></tr>
          <tr><th scope="row">Test</th><td>696</td><td>12</td><td>6</td><td>6</td></tr>
        </tbody>
      </table>
      <p class="callout">The training split contains 50 examples with at least two signals out of 5,406 rows. The small count makes performance on these cases easy to miss in an aggregate score.</p>
      <p class="caption"><a href="${docs}/domain-dataset-v4.md#size">Source: V4 dataset split and signal counts</a></p>
    </section>
    <section id="v4-training-resume">
      <h2>How the V4 training run resumed</h2>
      <p class="lede">We trained the LoRA adapter in FP32 on two T4 GPUs. The full epoch took two Kaggle sessions and completed at 676 optimizer updates.</p>
      <ol class="flow">
        <li><b>01</b>Start training</li><li><b>02</b>Save at step 350</li><li><b>03</b>Stop at step 387</li>
        <li><b>04</b>Resume from step 350</li><li><b>05</b>Finish at step 676</li>
      </ol>
      <div class="grid two">
        <article><h3>What the checkpoint restored</h3><p>The checkpoint preserved the adapter weights, the optimizer state and the position in the dataset. The resumed session performed 326 updates after loading step 350.</p></article>
        <article><h3>Recorded training time</h3><p>The first process ran for 11.4 hours and the second for 9.75 hours. The 37 updates made after the saved checkpoint were discarded.</p></article>
      </div>
      <p class="caption"><a href="${docs}/finetuning-v4-results.md#the-completed-epoch">Source: V4 training record</a> · <a href="${docs}/kaggle-finetuning.md#training-approach">Training approach</a></p>
    </section>`);

  document.querySelector("#v4-comparison").insertAdjacentHTML("afterend", `
    <section id="v4-guard-rescore">
      <h2>What the first relevance guard changed</h2>
      <p class="lede">After finding off-topic citations, we applied the original relevance guard to the 54 saved V4 test answers and scored them again.</p>
      <table class="data-table grouped">
        <thead><tr><th scope="col">Metric</th><th scope="col">Saved answer</th><th scope="col">After historical guard</th></tr></thead>
        <tbody>
          ${pair("Relevance failures · lower is better", 2, 0, 54, ["Saved", "Guard applied"])}
          ${pair("Marked evidence unavailable when expected", 10, 12, 12, ["Saved", "Guard applied"])}
          ${pair("Valid answer schema", 54, 54, 54, ["Saved", "Guard applied"])}
        </tbody>
      </table>
      <p class="callout">We reused the saved generations for this comparison. The current validator checks each cited record and keeps validation failures visible after repair.</p>
      <p class="caption"><a href="${docs}/finetuning-v4-results.md#the-historical-runtime-guard">Source: historical guard rescore</a></p>
    </section>`);

  document.querySelector("#targeted-rerun").insertAdjacentHTML("afterend", `
    <section id="failure-analysis">
      <h2>Three failures that shaped VERA</h2>
      <table class="data-table failure-table">
        <thead><tr><th scope="col">What failed</th><th scope="col">How we responded</th><th scope="col">What the evidence supports</th></tr></thead>
        <tbody>
          <tr><th scope="row">Alert counting<br /><small>Step 400: 1/8 passed</small></th><td>V4 added controlled replays with up to three signals. The runtime keeps detector counts separate from model prose.</td><td>We have no matched rerun of those eight cases with V4.</td></tr>
          <tr><th scope="row">In-domain refusals<br /><small>Step 400: 19/30</small></th><td>We separated intent assessment from source retrieval and preserve exact subjects when the system has a matching record.</td><td>Both local artifacts handled the targeted definition and scope checks. That is not a new 30-case rate.</td></tr>
          <tr><th scope="row">Off-topic citations<br /><small>V4: 2/54</small></th><td>The validator checks each cited record. A missing exact identifier requires abstention when there are no matching records or events.</td><td>The base model abstained on the local missing-ID rerun. Citation errors remain on other requests.</td></tr>
        </tbody>
      </table>
    </section>`);
})();
