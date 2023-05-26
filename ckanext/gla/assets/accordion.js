const accordionHeadings = document.querySelectorAll('.accordion__heading');

accordionHeadings.forEach(accordionHeading => {
    accordionHeading.addEventListener('click', () => {
        accordionHeading.parentElement.classList.toggle('active');
    });
});
