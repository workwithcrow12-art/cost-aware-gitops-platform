package main

import (
	"io"
	"net/http/httptest"
	"strconv"
	"sync"
	"testing"
)

func TestConcurrentDeploymentSnapshotsRenderConsistently(t *testing.T) {
	original := deploymentDetailsMap.Load()
	if original != nil {
		t.Cleanup(func() { deploymentDetailsMap.Store(original) })
	}
	deploymentDetailsMap.Store(map[string]string{"HOSTNAME": "0", "CLUSTERNAME": "0", "ZONE": "0"})
	var workers sync.WaitGroup
	workers.Add(1)
	go func() {
		defer workers.Done()
		for i := 0; i < 100; i++ {
			value := strconv.Itoa(i)
			deploymentDetailsMap.Store(map[string]string{
				"HOSTNAME": value, "CLUSTERNAME": value, "ZONE": value,
			})
		}
	}()
	for i := 0; i < 4; i++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			request := httptest.NewRequest("GET", "http://example.test/", nil)
			for j := 0; j < 100; j++ {
				data := injectCommonTemplateData(request, nil)
				details := data["deploymentDetails"].(map[string]string)
				if details["HOSTNAME"] != details["CLUSTERNAME"] || details["HOSTNAME"] != details["ZONE"] {
					t.Error("template observed a partially populated snapshot")
				}
				if err := templates.ExecuteTemplate(io.Discard, "footer", data); err != nil {
					t.Error(err)
				}
			}
		}()
	}
	workers.Wait()
}
