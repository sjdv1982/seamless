case "$-" in
  *i*)
    if [ -n "${BASH_VERSION:-}" ] && command -v seamless-mode-bind.sh >/dev/null 2>&1; then
      source "$(command -v seamless-mode-bind.sh)"
    fi
    ;;
esac
