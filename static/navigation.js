let map;
let marker;
let savedMarkers = [];
let currentMarker = null;
let places = []; // Declare a global array to store places
let geofences = {}; // Store geofences for saved places

// Initialize the map
function initMap() {
    map = L.map('map').setView([12.9716, 77.5946], 13); // Bengaluru coordinates

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    map.on('click', function (e) {
        if (currentMarker) {
            map.removeLayer(currentMarker);
        }
        currentMarker = L.marker([e.latlng.lat, e.latlng.lng]).addTo(map);
        document.getElementById('latitude').value = e.latlng.lat;
        document.getElementById('longitude').value = e.latlng.lng;
    });

    fetchSavedPlaces();  // Fetch saved places when the map is loaded
    getCurrentLocation();
}

// Fetch saved places from the server and create geofences
function fetchSavedPlaces() {
    fetch('/api/places')
        .then(response => response.json())
        .then(data => {
            savedMarkers.forEach(marker => map.removeLayer(marker)); // Remove old markers
            savedMarkers = [];
            geofences = {}; // Clear old geofences
            places = data; // Populate the places array with fetched data

            data.forEach(place => {
                const marker = L.marker([place.lat, place.lng]).addTo(map)
                    .bindPopup(place.name);
                savedMarkers.push(marker);

                // Create a geofence if the place is "Home"
                if (place.name === "Home") {
                    const circle = L.circle([place.lat, place.lng], { radius: 1000 }).addTo(map);
                    geofences["Home"] = circle;
                }

                // Add to dropdown lists
                const sourceOption = document.createElement('option');
                sourceOption.value = place.name;
                sourceOption.textContent = place.name;
                document.getElementById('source').appendChild(sourceOption);

                const destinationOption = document.createElement('option');
                destinationOption.value = place.name;
                destinationOption.textContent = place.name;
                document.getElementById('destination').appendChild(destinationOption);
            });
        });
}

// Check if current location is within the geofence
function checkGeofencing(currentLat, currentLng) {
    if (geofences["Home"]) {
        const distance = map.distance([currentLat, currentLng], geofences["Home"].getLatLng());
        if (distance > 1000) { // 1 km radius
            alert("You are outside the geofence for 'Home'.");
        }
    }
}

function getCurrentLocation() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function (position) {
            const currentLat = position.coords.latitude;
            const currentLng = position.coords.longitude;

            // Add custom icon for current location
            const currentLocationIcon = L.icon({
                iconUrl: 'https://png.pngtree.com/png-vector/20230320/ourmid/pngtree-you-are-here-location-pointer-vector-png-image_6656543.png',
                iconSize: [70, 70],
                iconAnchor: [16, 32],
                popupAnchor: [0, -32]
            });

            // Add current location marker
            const currentLocationMarker = L.marker([currentLat, currentLng], {
                icon: currentLocationIcon
            })
                .addTo(map)
                .bindPopup("You are here")
                .openPopup();

            // Update the dropdown
            const sourceDropdown = document.getElementById('source');
            
            // Remove existing "Current Location" if present
            const existingCurrentLocation = document.querySelector('#source option[data-current="true"]');
            if (existingCurrentLocation) {
                sourceDropdown.removeChild(existingCurrentLocation);
            }

            // Add "Current Location" at the top
            const currentLocationOption = document.createElement('option');
            currentLocationOption.value = `current:${currentLat},${currentLng}`;
            currentLocationOption.textContent = 'Current Location';
            currentLocationOption.dataset.current = 'true';
            sourceDropdown.insertBefore(currentLocationOption, sourceDropdown.firstChild);

            // Optionally, zoom the map to current location
            map.setView([currentLat, currentLng], 13);

            // Check geofencing for "Home"
            checkGeofencing(currentLat, currentLng);
        }, function () {
            alert("Geolocation failed or permission denied.");
        });
    } else {
        alert("Geolocation is not supported by this browser.");
    }
}

window.onload = initMap;




// Save a new place
document.getElementById('savePlaceBtn').addEventListener('click', function () {
    const placeName = document.getElementById('placeName').value;
    if (!currentMarker || !placeName.trim()) {
        alert('Please select a place on the map and provide a name.');
        return;
    }

    const { lat, lng } = currentMarker.getLatLng();

    // Send POST request to save the place
    fetch('/navigation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ place_name: placeName, latitude: lat, longitude: lng })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Update the dropdown and map after successful place saving
            fetchSavedPlaces();  // Fetch the updated list of places
            currentMarker = null;
            alert('Place saved successfully!');
        } else {
            alert('Failed to save place.');
        }
    });
});

// Find route between two places
function calculateRoute() {
    const source = document.getElementById("source").value;
    const destination = document.getElementById("destination").value;

    // Ensure both source and destination are selected
    if (!source || !destination) {
        alert("Please select both source and destination.");
        return;
    }

    let sourceLatLng;
    if (source.startsWith('current:')) {
        // Decode the current location from the dropdown value
        const [lat, lng] = source.split(':')[1].split(',').map(Number);
        sourceLatLng = L.latLng(lat, lng);
    } else {
        // Find the source in the saved places
        const sourcePlace = places.find(p => p.name === source);
        if (sourcePlace) {
            sourceLatLng = L.latLng(sourcePlace.lat, sourcePlace.lng);
        } else {
            alert("Source place not found.");
            return;
        }
    }

    const destinationPlace = places.find(p => p.name === destination);
    if (!destinationPlace) {
        alert("Destination place not found.");
        return;
    }

    // Create the route between source and destination
    const routeControl = L.Routing.control({
        waypoints: [
            sourceLatLng,
            L.latLng(destinationPlace.lat, destinationPlace.lng)
        ],
        routeWhileDragging: true,
        createGeocoder: function () {
            return L.DomUtil.create('div', 'leaflet-routing-alt');
        }
    }).addTo(map);

    // Adjust the map to fit the route
    map.fitBounds(routeControl.getBounds());
}



window.onload = initMap;
