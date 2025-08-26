document.addEventListener("DOMContentLoaded", () => {
    const countrySelect = document.getElementById("country");
    const regionSelect = document.getElementById("region");
    const citySelect = document.getElementById("city");
    const zoneSelect = document.getElementById("zone");

    // --- Charger les pays au chargement ---
    fetch("/location/countries")
        .then(res => res.json())
        .then(data => {
            data.forEach(c => {
                const opt = document.createElement("option");
                opt.value = c.code;
                opt.textContent = c.name;
                countrySelect.appendChild(opt);
            });
        })
        .catch(err => console.error("Erreur chargement pays:", err));

    // --- Quand on change le pays, charger les régions ---
    countrySelect.addEventListener("change", () => {
        regionSelect.innerHTML = '<option value="">Sélectionner un pays d\'abord</option>';
        citySelect.innerHTML = '<option value="">Sélectionner une région d\'abord</option>';
        zoneSelect.innerHTML = '<option value="">Sélectionner une ville d\'abord</option>';

        regionSelect.disabled = true;
        citySelect.disabled = true;
        zoneSelect.disabled = true;

        if (!countrySelect.value) return;

        fetch(`/location/regions/${countrySelect.value}`)
            .then(res => res.json())
            .then(data => {
                data.forEach(r => {
                    const opt = document.createElement("option");
                    opt.value = r.code;
                    opt.textContent = r.name;
                    regionSelect.appendChild(opt);
                });
                regionSelect.disabled = false;
            })
            .catch(err => console.error("Erreur chargement régions:", err));
    });

    // --- Quand on change la région, charger les villes ---
    regionSelect.addEventListener("change", () => {
        citySelect.innerHTML = '<option value="">Sélectionner une région d\'abord</option>';
        zoneSelect.innerHTML = '<option value="">Sélectionner une ville d\'abord</option>';

        citySelect.disabled = true;
        zoneSelect.disabled = true;

        if (!regionSelect.value) return;

        fetch(`/location/cities/${countrySelect.value}/${regionSelect.value}`)
            .then(res => res.json())
            .then(data => {
                data.forEach(c => {
                    const opt = document.createElement("option");
                    opt.value = c.id;
                    opt.textContent = c.name;
                    citySelect.appendChild(opt);
                });
                citySelect.disabled = false;
            })
            .catch(err => console.error("Erreur chargement villes:", err));
    });

    // --- Quand on change la ville, activer la zone ---
    citySelect.addEventListener("change", () => {
        zoneSelect.innerHTML = '<option value="">Sélectionner une ville d\'abord</option>';
        zoneSelect.disabled = true;

        if (!citySelect.value) return;

        zoneSelect.disabled = false;
        const manualOption = document.createElement("option");
        manualOption.value = "manual";
        manualOption.textContent = "↳ Saisir manuellement...";
        zoneSelect.appendChild(manualOption);
    });

    // --- Saisie manuelle de la zone ---
    zoneSelect.addEventListener("change", function() {
        if (this.value === "manual") {
            const manualZone = prompt("Veuillez saisir le nom de la zone/quartier:");
            if (manualZone) {
                const newOption = document.createElement("option");
                newOption.value = manualZone;
                newOption.textContent = manualZone;
                newOption.selected = true;
                zoneSelect.appendChild(newOption);
            }
            this.selectedIndex = 0;
        }
    });
});