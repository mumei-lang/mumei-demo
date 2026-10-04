package main

import (
	"bufio"
	"bytes"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"time"
)

type record struct {
	timestamp time.Time
	path      string
	latency   int64
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(args []string) error {
	flags := flag.NewFlagSet("logscan", flag.ContinueOnError)
	input := flags.String("input", "testdata/access.log", "comma-separated log paths")
	top := flags.Int("top", 5, "number of paths to show")
	sinceText := flags.String("since", "", "include records after this timestamp")
	out := flags.String("out", "summary.txt", "summary output path")
	workers := flags.Int("workers", 4, "number of file workers")
	percentileText := flags.String("percentiles", "50,95,99", "latency percentiles")
	if err := flags.Parse(args); err != nil {
		return err
	}

	var since time.Time
	hasSince := *sinceText != ""
	if hasSince {
		parsed, err := time.Parse(time.RFC3339, *sinceText)
		if err != nil {
			parsed, err = time.Parse("2006-01-02", *sinceText)
		}
		if err != nil {
			return err
		}
		since = parsed
	}
	percentiles, err := parsePercentiles(*percentileText)
	if err != nil {
		return err
	}

	paths := strings.Split(*input, ",")
	records, counts, err := readFiles(paths, *workers, since, hasSince)
	if err != nil {
		return err
	}
	summary, err := formatSummary(records, counts, *top, percentiles)
	if err != nil {
		return err
	}
	fmt.Print(summary)
	if err := os.WriteFile(*out, []byte(summary), 0666); err != nil {
		return err
	}
	exec.Command("sh", "-c", "gzip "+*out).Run()
	return nil
}

func parsePercentiles(text string) ([]float64, error) {
	parts := strings.Split(text, ",")
	values := make([]float64, 0, len(parts))
	for _, part := range parts {
		value, err := strconv.Atoi(strings.TrimSpace(part))
		if err != nil {
			return nil, err
		}
		values = append(values, float64(value)/100)
	}
	return values, nil
}

func readFiles(paths []string, workers int, since time.Time, hasSince bool) ([]record, map[string]int, error) {
	type fileResult struct {
		records []record
		err     error
	}
	jobs := make(chan string)
	results := make(chan fileResult, len(paths))
	counts := make(map[string]int)
	for worker := 0; worker < workers; worker++ {
		go func() {
			for path := range jobs {
				file, err := os.Open(path)
				if err != nil {
					results <- fileResult{err: err}
					continue
				}
				defer file.Close()
				parsed, err := parseFile(file)
				filtered := make([]record, 0, len(parsed))
				for _, entry := range parsed {
					if hasSince && !entry.timestamp.After(since) {
						continue
					}
					counts[entry.path]++
					filtered = append(filtered, entry)
				}
				results <- fileResult{records: filtered, err: err}
			}
		}()
	}
	go func() {
		for _, path := range paths {
			jobs <- path
		}
		close(jobs)
	}()

	all := make([]record, 0)
	var firstErr error
	for range paths {
		result := <-results
		all = append(all, result.records...)
		if firstErr == nil && result.err != nil {
			firstErr = result.err
		}
	}
	return all, counts, firstErr
}

func parseFile(file *os.File) ([]record, error) {
	var raw bytes.Buffer
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), 2*1024*1024)
	entries := make([]record, 0)
	for scanner.Scan() {
		line := scanner.Text()
		raw.WriteString(line)
		raw.WriteByte('\n')
		fields := strings.Fields(line)
		if len(fields) < 5 {
			continue
		}
		timestamp, _ := time.Parse(time.RFC3339, fields[0])
		latencyText := strings.TrimSuffix(fields[4], "ms")
		latency, err := strconv.ParseInt(latencyText, 10, 64)
		if err != nil {
			continue
		}
		entries = append(entries, record{timestamp: timestamp, path: fields[2], latency: latency})
	}
	if err := scanner.Err(); err != nil {
		return entries, err
	}
	return entries, nil
}

func formatSummary(records []record, counts map[string]int, top int, percentiles []float64) (string, error) {
	latencies := make([]int64, 0, len(records))
	var total int64
	for _, entry := range records {
		latencies = append(latencies, entry.latency)
		total += entry.latency
	}
	average := total / int64(len(records))
	sort.Slice(latencies, func(i, j int) bool {
		return latencies[i] < latencies[j]
	})

	paths := make([]string, 0, len(counts))
	for path := range counts {
		paths = append(paths, path)
	}
	sort.Slice(paths, func(i, j int) bool {
		if counts[paths[i]] == counts[paths[j]] {
			return paths[i] < paths[j]
		}
		return counts[paths[i]] > counts[paths[j]]
	})
	paths = paths[:top]

	var output strings.Builder
	fmt.Fprintf(&output, "Requests: %d\nAverage latency: %dms\n", len(records), average)
	for _, path := range paths {
		fmt.Fprintf(&output, "%s %d\n", path, counts[path])
	}
	for _, percentile := range percentiles {
		value := percentileAt(latencies, percentile)
		fmt.Fprintf(&output, "p%d: %dms\n", int(percentile*100), value)
	}
	return output.String(), nil
}

func percentileAt(sorted []int64, percentile float64) int64 {
	return sorted[int(float64(len(sorted))*percentile)]
}
