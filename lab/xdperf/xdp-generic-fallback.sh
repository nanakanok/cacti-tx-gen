#!/bin/bash
# Patch xdperf to add XDPGenericMode fallback for veth interfaces.
# The probe code (probe/xdp.go) already has this fallback but the
# main runner (xdperf/xdperf.go) does not.

FILE=pkg/xdperf/xdperf.go

# Find the line number of the first "if err != nil {" after "dummy XDP Prog attachment"
MARKER_LINE=$(grep -n "dummy XDP Prog attachment" "$FILE" | head -1 | cut -d: -f1)
if [ -z "$MARKER_LINE" ]; then
    echo "ERROR: could not find marker comment"
    exit 1
fi

# Find the "if err != nil {" line after the marker
ERR_LINE=$(tail -n +"$MARKER_LINE" "$FILE" | grep -n "if err != nil {" | head -1 | cut -d: -f1)
ERR_LINE=$((MARKER_LINE + ERR_LINE - 1))

echo "Patching $FILE at line $ERR_LINE (after marker at line $MARKER_LINE)"

# Insert generic mode fallback before the error check
sed -i "${ERR_LINE}i\\
\\tif err != nil {\\
\\t\\tl, err = link.AttachXDP(link.XDPOptions{\\
\\t\\t\\tProgram:   rxprog,\\
\\t\\t\\tInterface: x.Device.Index,\\
\\t\\t\\tFlags:     link.XDPGenericMode,\\
\\t\\t})\\
\\t}" "$FILE"

echo "Patch applied. Verifying..."
grep -A 15 "dummy XDP Prog attachment" "$FILE"
