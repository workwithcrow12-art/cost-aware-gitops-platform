/*
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 */

package hipstershop;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import hipstershop.Demo.Ad;
import hipstershop.Demo.AdRequest;
import hipstershop.Demo.AdResponse;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import java.io.IOException;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class AdServiceTest {

  @Test
  void returnsContextualAdsForKnownCategories() {
    AdService service = AdService.getInstance();
    Collection<Ad> hairAds = service.getAdsByCategory("hair");
    assertFalse(hairAds.isEmpty());
    assertTrue(
        hairAds.stream().anyMatch(ad -> ad.getRedirectUrl().equals("/product/2ZYFJ3GM2N")));
  }

  @Test
  void returnsRandomAdsWhenCategoryHasNoMatches() {
    AdService service = AdService.getInstance();
    assertTrue(service.getAdsByCategory("unknown-category").isEmpty());
    List<Ad> randomAds = service.getRandomAds();
    assertEquals(2, randomAds.size());
    for (Ad ad : randomAds) {
      assertFalse(ad.getRedirectUrl().isEmpty());
      assertFalse(ad.getText().isEmpty());
    }
  }

  @Test
  void grpcGetAdsServesContextualAndFallbackResponses() throws IOException, InterruptedException {
    Server server =
        ServerBuilder.forPort(0).addService(new AdService.AdServiceImpl()).build().start();
    ManagedChannel channel =
        ManagedChannelBuilder.forAddress("127.0.0.1", server.getPort()).usePlaintext().build();
    try {
      AdServiceGrpc.AdServiceBlockingStub stub = AdServiceGrpc.newBlockingStub(channel);

      AdResponse contextual =
          stub.getAds(AdRequest.newBuilder().addContextKeys("clothing").build());
      assertNotNull(contextual);
      assertFalse(contextual.getAdsList().isEmpty());
      assertTrue(
          contextual.getAdsList().stream()
              .anyMatch(ad -> ad.getRedirectUrl().equals("/product/66VCHSJNUP")));

      AdResponse fallback =
          stub.getAds(AdRequest.newBuilder().addContextKeys("nonexistent").build());
      assertEquals(2, fallback.getAdsCount());

      AdResponse emptyRequest = stub.getAds(AdRequest.getDefaultInstance());
      assertEquals(2, emptyRequest.getAdsCount());
    } finally {
      channel.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
      server.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
