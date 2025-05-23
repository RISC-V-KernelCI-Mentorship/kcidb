# KCIDB cloud deployment - Cloud Functions
#
if [ -z "${_FUNCTIONS_SH+set}" ]; then
declare _FUNCTIONS_SH=

. function.sh
. misc.sh

# Output deployment environment for Cloud Functions
# Args: --format=yaml|sh
#       --project=ID
#       --log-level=NAME
#       --cache-bucket-name=NAME
#       --optimize=PYTHONOPTIMIZE
#       --heavy-asserts=true|false
#       --new-topic=NAME --new-load-subscription=NAME
#       --updated-publish=true|false
#       --updated-urls-publish=true|false
#       --updated-topic=NAME
#       --load-queue-trigger-topic=NAME
#       --purge-db-trigger-topic=NAME
#       --archive-trigger-topic=NAME
#       --updated-urls-topic=NAME
#       --cache-bucket-name=NAME
#       --cache-redirector-url=URL
#       --spool-collection-path=PATH
#       --extra-cc=ADDRS
#       --smtp-to-addrs=ADDRS --smtp-password-secret=NAME
#       --smtp-topic=NAME --smtp-subscription=NAME
#       --pgpass-secret=NAME
#       --op-database=SPEC
#       --ar-database=SPEC
#       --sm-database=SPEC
#       --database=SPEC
#       --clean-test-databases=SPEC_LIST
#       --empty-test-databases=SPEC_LIST
function functions_env() {
    declare params
    params="$(getopt_vars format \
                          project \
                          log_level \
                          optimize \
                          heavy_asserts \
                          new_topic new_load_subscription \
                          updated_publish \
                          updated_urls_publish \
                          updated_topic \
                          load_queue_trigger_topic \
                          purge_db_trigger_topic \
                          archive_trigger_topic \
                          updated_urls_topic \
                          spool_collection_path \
                          extra_cc \
                          smtp_to_addrs smtp_password_secret \
                          smtp_topic smtp_subscription \
                          pgpass_secret \
                          cache_bucket_name \
                          cache_redirector_url \
                          op_database \
                          ar_database \
                          sm_database \
                          database \
                          clean_test_databases \
                          empty_test_databases \
                          -- "$@")"
    eval "$params"
    declare -A env=(
        [GCP_PROJECT]="$project"
        [KCIDB_LOG_LEVEL]="$log_level"
        [PYTHONOPTIMIZE]="${optimize}"
        [KCIDB_LOAD_QUEUE_TOPIC]="$new_topic"
        [KCIDB_LOAD_QUEUE_SUBSCRIPTION]="$new_load_subscription"
        [KCIDB_LOAD_QUEUE_MSG_MAX]="1024"
        [KCIDB_LOAD_QUEUE_OBJ_MAX]="16384"
        [KCIDB_LOAD_QUEUE_TIMEOUT_SEC]="60"
        [KCIDB_PGPASS_SECRET]="$pgpass_secret"
        [KCIDB_OPERATIONAL_DATABASE]="$op_database"
        [KCIDB_ARCHIVE_DATABASE]="$ar_database"
        [KCIDB_SAMPLE_DATABASE]="$sm_database"
        [KCIDB_DATABASE]="$database"
        [KCIDB_CLEAN_TEST_DATABASES]="$clean_test_databases"
        [KCIDB_EMPTY_TEST_DATABASES]="$empty_test_databases"
        [KCIDB_UPDATED_QUEUE_TOPIC]="$updated_topic"
        [KCIDB_LOAD_QUEUE_TRIGGER_TOPIC]="$load_queue_trigger_topic"
        [KCIDB_PURGE_DB_TRIGGER_TOPIC]="$purge_db_trigger_topic"
        [KCIDB_ARCHIVE_TRIGGER_TOPIC]="$archive_trigger_topic"
        [KCIDB_UPDATED_URLS_TOPIC]="$updated_urls_topic"
        [KCIDB_SELECTED_SUBSCRIPTIONS]=""
        [KCIDB_SPOOL_COLLECTION_PATH]="$spool_collection_path"
        [KCIDB_SMTP_HOST]="smtp.gmail.com"
        [KCIDB_SMTP_PORT]="587"
        [KCIDB_SMTP_USER]="bot@kernelci.org"
        [KCIDB_SMTP_PASSWORD_SECRET]="$smtp_password_secret"
        [KCIDB_SMTP_FROM_ADDR]="bot@kernelci.org"
        [KCIDB_CACHE_BUCKET_NAME]="$cache_bucket_name"
        [KCIDB_CACHE_REDIRECTOR_URL]="$cache_redirector_url"
    )
    if [ -n "$extra_cc" ]; then
        env[KCIDB_EXTRA_CC]="$extra_cc"
    fi
    if [ -n "$smtp_to_addrs" ]; then
        env[KCIDB_SMTP_TO_ADDRS]="$smtp_to_addrs"
    fi
    if [ -n "$smtp_topic" ]; then
        env[KCIDB_SMTP_TOPIC]="$smtp_topic"
        env[KCIDB_SMTP_SUBSCRIPTION]="$smtp_subscription"
    fi
    if "$heavy_asserts"; then
        env[KCIDB_IO_HEAVY_ASSERTS]="1"
        env[KCIDB_HEAVY_ASSERTS]="1"
    fi
    if "$updated_publish"; then
        env[KCIDB_UPDATED_PUBLISH]="1"
    fi
    if "$updated_urls_publish"; then
        env[KCIDB_UPDATED_URLS_PUBLISH]="1"
    fi
    if [ "$format" == "yaml" ]; then
        # Silly Python and its significant whitespace
        sed -E 's/^[[:blank:]]+//' <<<'
            import sys, yaml
            args = sys.argv[1::]
            middle = len(args) >> 1
            yaml.dump(dict(zip(args[:middle], args[middle:])),
                      stream=sys.stdout)
        ' | python3 - "${!env[@]}" "${env[@]}"
    elif [ "$format" == "sh" ]; then
        declare name
        for name in "${!env[@]}"; do
            echo "export $name=${env[$name]@Q}"
        done
    else
        echo "Unknown environment output format: ${format@Q}" >&2
        exit 1
    fi
}

# Deploy Cloud Functions
# Args: --sections=GLOB
#       --project=NAME --prefix=PREFIX --source=PATH
#       --load-queue-trigger-topic=NAME
#       --pick-notifications-trigger-topic=NAME
#       --purge-db-trigger-topic=NAME
#       --updated-urls-topic=NAME
#       --updated-topic=NAME
#       --spool-collection-path=PATH
#       --cache-redirect-function-name=NAME
#       --env-yaml=YAML
#       --archive-trigger-topic=NAME
function functions_deploy() {
    declare params
    params="$(getopt_vars sections project prefix source \
                          load_queue_trigger_topic \
                          pick_notifications_trigger_topic \
                          purge_db_trigger_topic \
                          updated_urls_topic \
                          updated_topic \
                          spool_collection_path \
                          cache_redirect_function_name \
                          env_yaml \
                          archive_trigger_topic \
                          -- "$@")"
    eval "$params"

    # Allow the App Engine service account to create its own tokens
    # so it can sign Google Cloud Storage URLs
    mute gcloud iam service-accounts add-iam-policy-binding \
        --quiet --project="$project" \
        "$project@appspot.gserviceaccount.com" \
        --role=roles/iam.serviceAccountTokenCreator \
        --member="serviceAccount:$project@appspot.gserviceaccount.com"

    # Create empty environment YAML
    declare env_yaml_file
    env_yaml_file=`mktemp --tmpdir kcidb_cloud_env.XXXXXXXX`
    # Store environment YAML
    echo -n "$env_yaml" >| "$env_yaml_file"

    # Deploy functions back-to-front pipeline-wise,
    # so compatibility is preserved in the process
    declare trigger_event="providers/cloud.firestore/eventTypes/"
    trigger_event+="document.create"
    declare trigger_resource="projects/$project/databases/(default)/documents/"
    trigger_resource+="${spool_collection_path}/{notification_id}"

    function_deploy "$sections" "$source" "$project" "$prefix" \
                    archive true \
                    --env-vars-file "$env_yaml_file" \
                    --trigger-topic "${archive_trigger_topic}" \
                    --memory 8192MB \
                    --max-instances=1 \
                    --timeout 540

    function_deploy "$sections" "$source" "$project" "$prefix" \
                    purge_db true \
                    --env-vars-file "$env_yaml_file" \
                    --trigger-topic "${purge_db_trigger_topic}" \
                    --memory 256MB \
                    --max-instances=1 \
                    --timeout 540

    function_deploy "$sections" "$source" "$project" "$prefix" \
                    pick_notifications true \
                    --env-vars-file "$env_yaml_file" \
                    --trigger-topic "${pick_notifications_trigger_topic}" \
                    --memory 256MB \
                    --max-instances=1 \
                    --timeout 540

    function_deploy "$sections" "$source" "$project" "$prefix" \
                    send_notification true \
                    --env-vars-file "$env_yaml_file" \
                    --trigger-event "${trigger_event}" \
                    --trigger-resource "${trigger_resource}" \
                    --memory 256MB \
                    --retry \
                    --max-instances=1 \
                    --timeout 540

    function_deploy "$sections" "$source" "$project" "$prefix" \
                    spool_notifications true \
                    --env-vars-file "$env_yaml_file" \
                    --trigger-topic "${updated_topic}" \
                    --memory 4096MB \
                    --max-instances=2 \
                    --timeout 540

    function_deploy "$sections" "$source" "$project" "$prefix" \
                    "$cache_redirect_function_name" false \
                    --env-vars-file "$env_yaml_file" \
                    --trigger-http \
                    --memory 256MB \
                    --max-instances=16 \
                    --timeout 30

    function_deploy "$sections" "$source" "$project" "$prefix" \
                    cache_urls true \
                    --env-vars-file "$env_yaml_file" \
                    --trigger-topic "${updated_urls_topic}" \
                    --memory 512MB \
                    --max-instances=1 \
                    --timeout 540

    function_deploy "$sections" "$source" "$project" "$prefix" \
                    load_queue true \
                    --env-vars-file "$env_yaml_file" \
                    --trigger-topic "${load_queue_trigger_topic}" \
                    --memory 1024MB \
                    --max-instances=4 \
                    --timeout 540
    # Remove the environment YAML file
    rm "$env_yaml_file"
}

# Withdraw or shutdown Cloud Functions
# Args: action
#       --sections=GLOB --project=NAME --prefix=PREFIX
#       --cache-redirect-function-name=NAME
function _functions_withdraw_or_shutdown() {
    declare -r action="$1"; shift
    declare params
    params="$(getopt_vars sections project prefix \
                          cache_redirect_function_name \
                          -- "$@")"
    eval "$params"
    "function_$action" "$sections" "$project" "$prefix" \
                       archive
    "function_$action" "$sections" "$project" "$prefix" \
                       purge_db
    "function_$action" "$sections" "$project" "$prefix" \
                       pick_notifications
    "function_$action" "$sections" "$project" "$prefix" \
                       send_notification
    "function_$action" "$sections" "$project" "$prefix" \
                       spool_notifications
    "function_$action" "$sections" "$project" "$prefix" \
                       "$cache_redirect_function_name"
    "function_$action" "$sections" "$project" "$prefix" \
                       cache_urls
    "function_$action" "$sections" "$project" "$prefix" \
                       load_queue
}

# Shutdown Cloud Functions
# Args: --sections=GLOB --project=NAME --prefix=PREFIX
#       --cache-redirect-function-name=NAME
function functions_shutdown() {
    _functions_withdraw_or_shutdown shutdown "$@"
}

# Withdraw Cloud Functions
# Args: --sections=GLOB --project=NAME --prefix=PREFIX
#       --cache-redirect-function-name=NAME
function functions_withdraw() {
    _functions_withdraw_or_shutdown withdraw "$@"
}

fi # _FUNCTIONS_SH
