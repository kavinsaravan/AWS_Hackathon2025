# Deployment reliability and dataset exports

Install the dependencies for the new tooling with
`python3 -m pip install -r scripts/requirements.txt`.

## Managed AWS deployments

The scoring route, refresh rule, refresh permission, and backup bucket are adopted
into the existing CloudFormation stack rather than recreated. Import templates
preserve the original YAML resources and outputs verbatim: CloudFormation's import
validation rejects changes to existing outputs, even equivalent intrinsic syntax.
EventBridge rules are imported by ARN. API route and Lambda permission imports use
the separate identifier fields returned by `get-template-summary`.

`scripts/reconcile_aws_backend.py` prepares the import template, identifiers,
previous template, and a verified copy of the live Lambda ZIP. It also prepares a
baseline stack update that declares that **same code**, its S3 release key, storage
environment, and existing S3 role policy. Establishing that baseline is required:
rolling back to the old placeholder-code template would overwrite the working API.

For another existing installation:

```sh
python3 scripts/reconcile_aws_backend.py --account ACCOUNT --api-id API_ID \
  --stack-name STACK --output-dir /private/tmp/safepath-reconciliation
```

Review and execute an IMPORT change set using the generated import template,
`resources-to-import.json`, and `import-parameters.json`. Use `import-template.yaml`
when present to preserve existing output syntax. Upload `baseline-lambda.zip` under
the bucket/key in `reconciliation-summary.json`, then review an UPDATE change set
using `baseline-template.json` and `baseline-parameters.json`. The import should
contain only Import actions; the baseline should modify only the Lambda and its
existing IAM role directly, with no deletions. Dependent ARN references may be
reevaluated because the function is updated; confirm that their names and resolved
ARNs remain unchanged. Verify the API afterward.

For subsequent releases:

```sh
bash scripts/package_routing_backend.sh /private/tmp/lambda-routing.zip
python3 scripts/deploy_aws_backend.py --account ACCOUNT --api-id API_ID \
  --stack-name STACK --lambda-zip /private/tmp/lambda-routing.zip \
  --backup-dir /private/tmp/safepath-deployment-backups
```

The default is a read-only preview. Add `--apply` to publish the reviewed release.
Each deployment gets a unique private subdirectory under the backup root, so reusing
that root never overwrites previous rollback artifacts. The ZIP checksum is checked
before upload. Deployments refuse unmanaged resources, code drift, replacements,
or direct updates outside the Lambda resource. CloudFormation may reevaluate
unchanged API/schedule ARN references; only those precise dependency changes are
allowed. Existing routes and schedules stay under
CloudFormation ownership.

CloudFormation handles failed stack updates. If the update completes but snapshot
warm-up or verification fails, the tool submits a reverse stack update restoring
the previous template and code parameters, then checks the restored code checksum.
Failures during rollback are explicitly reported with retained artifacts and a
`rollback_failed` journal status; they are never reported as successful recovery.
Unreferenced release objects are retained rather than risking deletion of backups.

## Dataset schema

The binary, production, final, and statistical generators now share one collection
and feature pipeline. Default CSVs have headers, sample IDs, coordinates, measured
crime/dispatch/hazard counts, time context, risk scores, thresholds, and labels.
A `.metadata.json` sidecar records source counts, source windows, seed, label policy,
and columns that must be excluded from training to avoid label leakage.

```sh
python3 scripts/generate_production_dataset.py --samples 10000 --seed 42 \
  --output /private/tmp/sf_safety_features.csv
```

Police incidents use a rolling 90-day window, dispatch calls use 72 hours, and open
311 reports use 30 days. All three required sources paginate; source errors or a
pagination limit abort generation instead of silently producing low-risk labels.
Spatial indexes count actual incidents within 200m for crime and 100m for calls and
311 reports. Seeded sampling gives exactly the requested count and excludes the
same approximate water areas as the earlier generators. This mask is not a street
network or an authoritative land polygon.

Labels are **heuristic proxies**, not observed outcomes or validated safety classes.
They are computed from documented weighted counts; no unsafe percentile is forced
and no nighttime label is randomly flipped. These are sampled locations, not
walking routes. `--labels-only` explicitly opts into the old headerless label export;
it discards the features and should not be used as a complete training dataset.

Coverage analysis uses nested list indexing, excludes invalid/out-of-bounds points,
and includes partial edge cells. Sample size alone does not prove that locations
represent city-wide risk or establish a classifier's accuracy.

## Tests

```sh
python3 -B -m unittest discover -s scripts/tests -v
python3 -B -m unittest discover -s backend/tests -v
node --test scripts/test_route_integration.cjs
```

The new offline suite checks backups, checksum verification, preview behavior,
failures throughout deployment, rollback failures, grid boundaries, reproducible
sampling, preserved CSV features, pagination, and source failures.

AWS documents [resource import support](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-import-supported-resources.html) for the resource types used here.
